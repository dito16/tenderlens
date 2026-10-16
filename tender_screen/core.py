"""Conservative, transparent PDF extraction and rule-based document triage.

No external connections, ML, official-register verification, or legal verdicts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import re

import pymupdf as fitz

from .fields import SCHEMA_VERSION, extract_typed_fields
from .context import classify, advance_conditions, clause_conditions, conflicts_for_review, additional_review_conflicts
from .audit import finalize
from .real_terms import extract_terms
from .pdf_layout import layout_for_page, derive_document_role
from .subject_price import build_normalized_card
from .domain_pipeline import build_domain_pipeline
from .processing_budget import ProcessingBudget, RunGuard, ProcessingLimitError


@dataclass(frozen=True)
class Rule:
    code: str
    title: str
    kind: str
    pattern: str
    explanation: str
    next_action: str


# Deliberately narrow phrases. A rule hit is evidence of wording, NOT verified fact.
RULES = (
    Rule("scope_uncertain", "Неопределённость объёмов", "risk",
         r"(?:объ[её]мы\s+(?:работ\s+)?(?:уточняются|ориентировочные)|ведомость\s+объ[её]мов\s+работ\s+(?:является\s+)?предварительн\w*)",
         "Объём может измениться после подготовки цены.",
         "Запросить окончательную ВОР и сверку по результатам осмотра."),
    Rule("unpriced_changes", "Работы без пересмотра цены", "risk",
         r"(?:без\s+увеличения\s+цен[ыа]|без\s+дополнительн\w*\s+оплат[ыа]|без\s+доплат[ыа])",
         "Найдена формулировка, ограничивающая оплату изменений.",
         "Согласовать порядок дополнительных работ и письменных изменений."),
    Rule("no_advance", "Аванс не предусмотрен", "risk",
         r"(?:аванс\s+(?:не\s+предусмотрен|отсутствует)|аванс\s*\d{1,3}(?:[.,]\d{1,2})?\s*%\s*не\s+предусмотрен|без\s+аванса|аванс\s*[:\-]\s*0\s*%)",
         "Финансирование работ может потребоваться до поступления оплаты.",
         "Сверить все документы, график финансирования и условия договора."),
    Rule("deferred_payment", "Отложенная оплата", "review",
         r"(?:оплата|расч[её]т)[^.!?\n]{0,120}?(?:в\s+течение|через)\s+\d{1,3}\s*(?:календарных|рабочих)?\s*дн(?:ей|я|ь)",
         "Найден срок отсрочки платежа, величина и момент отсчёта требуют проверки.",
         "Рассчитать кассовый разрыв с учётом поставок и фонда оплаты труда."),
    Rule("retention", "Удержание оплаты", "review",
         r"(?:удержани[ея]|retention)\s*(?:в\s+размере\s*)?\d{1,2}(?:[.,]\d+)?\s*%",
         "Часть оплаты может удерживаться на условиях договора.",
         "Проверить срок, основания и порядок возврата удержания."),
    Rule("night_access", "Ограниченные условия производства", "review",
         r"(?:в\s+ночное\s+время|в\s+действующем\s+(?:здании|офисе|магазине)|пропускн\w+\s+режим)",
         "Условия объекта могут влиять на производительность и себестоимость.",
         "Уточнить смены, допуски, простои и логистику материалов."),
    Rule("sro", "Условие о СРО", "requirement", r"\bСРО\b",
         "В документах упоминается СРО. Применимость требования зависит от роли и работ.",
         "Проверить точное условие закупки и его применимость к компании."),
    Rule("security", "Обеспечение или гарантия", "requirement",
         r"(?:обеспечени[ея]\s+(?:заявки|исполнения)|банковск\w*\s+гаранти\w*)",
         "Возможны финансовые требования к участнику.",
         "Подтвердить размер, вид, срок и допустимость обеспечения."),
    Rule("site_visit", "Осмотр объекта", "requirement",
         r"(?:обязательн\w*\s+осмотр\w*\s+объект\w*|осмотр\s+объекта\s+обязателен)",
         "Осмотр может быть условием допуска и основой проверки ВОР.",
         "Уточнить порядок регистрации и оформить результаты осмотра."),
    Rule("nonbinding", "Необязательность заключения договора", "review",
         r"(?:не\s+является\s+(?:офертой|обязательством)|вправе\s+отменить\s+(?:закупку|процедуру))",
         "Публикация закупки не обязательно означает присуждение договора.",
         "Выяснить этап закупки, критерии отбора и порядок заключения договора."),
    Rule("closeout", "Условия приёмки", "info", r"\bКС[-–]\s*[23]\b",
         "В документах обнаружены формы приёмки строительных работ.",
         "Проверить комплект актов, исполнительную документацию и сроки согласования."),
)

FIELDS = (
    ("deadline", "Крайний срок подачи",
     r"(?:подач[аиу]\s+(?:заявок|предложений)|при[её]м\s+(?:заявок|предложений))[^.\n]{0,120}?\b(?:до|по)\s+\d{1,2}[.]\d{1,2}[.]\d{4}"),
    ("budget", "Бюджет / цена", r"(?:бюджет\s+закупки|начальн\w*\s+(?:максимальн\w*\s+)?цена|цена\s+договора)[^.\n]{0,85}?\d[\d\s\u00a0]{2,}\s*(?:руб|₽)"),
    ("duration", "Срок выполнения", r"(?:срок\s+(?:выполнения|проведения)\s+работ)[^.\n]{0,100}?\d{1,3}\s*(?:календарных|рабочих)?\s*(?:дней|месяц[а-я]*)"),
    ("payment", "Условия оплаты", r"(?:оплат[аыуе]\s+(?:производится|осуществляется)|расч[её]ты\s+за\s+работы)"),
    ("scope", "Предмет работ", r"(?:объект\s+закупки\s*:\s*[^.!?]{8,115}|"
     r"подрядчик\s+(?:обязуется\s+)?выполн(?:ить|яет)\s+[^.!?]{8,115}|"
     r"объект\s*:\s*[^.!?]{8,115})"),
)


def normalize_with_offsets(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Normalize page text while retaining a mapping to *raw extracted text*.

    The offset map is one (start, exclusive_end) raw-text pair per character
    of normalized text. It is NOT a mapping to PDF glyph coordinates. A soft
    hyphen is removed; whitespace runs become one space, excluding leading and
    trailing whitespace. Preserve the raw extraction order from PyMuPDF.
    """
    characters: list[str] = []
    raw_ranges: list[tuple[int, int]] = []
    pending_space: int | None = None
    for index, character in enumerate(text):
        if character == "\u00ad":
            continue
        if character.isspace():
            if characters and pending_space is None:
                pending_space = index
            continue
        if pending_space is not None:
            characters.append(" ")
            raw_ranges.append((pending_space, index))
            pending_space = None
        characters.append(character)
        raw_ranges.append((index, index + 1))
    return "".join(characters), raw_ranges


def normalize(text: str) -> str:
    """Legacy-compatible normalized search text (not raw PDF offsets)."""
    return re.sub(r"\s+", " ", text.replace("\u00ad", "")).strip()


def snippet(text: str, start: int, end: int, radius: int = 115) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return ("…" if left else "") + text[left:right].strip() + ("…" if right < len(text) else "")


def extract_pdf(path: Path, *, guard: RunGuard | None = None) -> dict:
    """Extract all pages or return a resource error, never a truncated success."""
    if guard is None:
        guard = RunGuard(ProcessingBudget())
    size = path.stat().st_size
    guard.checkpoint()
    if size > guard.budget.max_file_bytes:
        raise ProcessingLimitError('pdf_file_byte_limit_exceeded')
    pages = []
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            guard.checkpoint()
            sha.update(chunk)
    with fitz.open(path) as doc:
        guard.before_file(len(doc),size)
        for ix, page in enumerate(doc):
            guard.checkpoint()
            raw = page.get_text("text", sort=True)
            if len(raw) > guard.budget.max_text_chars_per_page:
                raise ProcessingLimitError('page_text_limit_exceeded')
            normalized = normalize(raw)
            # A short readable page is not an image-only page. No OCR is run.
            searchable = bool(normalized)
            # Existing R4 text/offset contract is preserved verbatim.
            # New layout data is additional, never fabricated when unavailable.
            geometry = layout_for_page(page, raw, normalized, ix + 1)
            guard.after_page(len(normalized))
            pages.append({"page": ix + 1, "text": normalized,
                          "raw_text": raw, "normalized_text": normalized,
                          "has_text": searchable,
                          "text_status": "searchable" if searchable else "no_searchable_text",
                          **geometry})
    return {
        "file": path.name,
        "sha256": sha.hexdigest(),
        "page_count": len(pages),
        "document_role": derive_document_role(pages),
        "pages": pages,
    }


def evidence_from_pages(documents: list[dict], pattern: str, max_per_document: int = 2) -> list[dict]:
    expr = re.compile(pattern, flags=re.IGNORECASE)
    evidence = []
    for document in documents:
        found = 0
        for page in document["pages"]:
            for hit in expr.finditer(page["text"]):
                # The normalized span is always valid for page["text"]. Raw
                # span is only advertised when it is independently reversible.
                item = {"file": document["file"], "page": page["page"],
                        "source_sha256": document.get("sha256"),
                        "quote": snippet(page["text"], hit.start(), hit.end()),
                        "match": hit.group(0),
                        "normalized_span": [hit.start(), hit.end()],
                        "span_basis": "normalized_page_text",
                        "span_status": "unavailable"}
                raw = page.get("raw_text")
                if isinstance(raw, str):
                    normalized, offsets = normalize_with_offsets(raw)
                    if normalized == page["text"] and hit.end() <= len(offsets):
                        raw_start = offsets[hit.start()][0]
                        raw_end = offsets[hit.end() - 1][1]
                        # Do not claim raw offsets that cannot be reconstructed.
                        if normalize(raw[raw_start:raw_end]) == hit.group(0):
                            item["raw_span"] = [raw_start, raw_end]
                            item["span_status"] = "verified"
                evidence.append(item)
                found += 1
                if found >= max_per_document:
                    break
            if found >= max_per_document:
                break
    return evidence


def analyze(documents: list[dict]) -> dict:
    findings = []
    for rule in RULES:
        evidence = evidence_from_pages(documents, rule.pattern)
        if not evidence:
            continue
        # Evaluate the *matched sentence*, not a page-level bag of keywords.
        # A negation is surfaced as wording for review, never a positive risk.
        classified = []
        for ev in evidence:
            doc = next(d for d in documents if d["file"] == ev["file"]
                       and d["sha256"] == ev["source_sha256"])
            page = next(p for p in doc['pages'] if p['page']==ev['page'])
            pol, reason = classify(rule.code, page['text'], *ev['normalized_span'])
            classified.append({**ev,'polarity':pol,'polarity_basis':reason})
        # Avoid mixing contrary statements under one asserted positive finding.
        positive = [e for e in classified if e['polarity'] not in ('explicit_negative','unclear')]
        review = [e for e in classified if e['polarity'] in ('explicit_negative','unclear')]
        if positive:
            # SRO occurring in design materials or an unrelated reference is
            # not an eligibility requirement. Do not headline a mere mention
            # as an affirmative requirement in the human report.
            asserted = any(e['polarity']=='explicit_positive' for e in positive)
            title = ('Требование членства в СРО (формулировка)' if asserted else
                     'Упоминание СРО (обязательность не подтверждена)') if rule.code=='sro' else rule.title
            kind = ('requirement' if asserted else 'info') if rule.code=='sro' else rule.kind
            findings.append({'id':rule.code,'title':title,'kind':kind,
                             'explanation':rule.explanation,'next_action':rule.next_action,
                             'evidence':positive})
        if review:
            # The 'no_advance' rule is itself a negative condition, so an
            # explicit negative remains a financing risk (but quote/old
            # revision is downgraded to review).
            current = rule.code=='no_advance'
            active = [e for e in review if current and e['polarity']=='explicit_negative']
            inactive = [e for e in review if e not in active]
            if active:
                findings.append({'id':rule.code,'title':rule.title,'kind':rule.kind,
                                 'explanation':rule.explanation,'next_action':rule.next_action,
                                 'evidence':active})
            if inactive:
                is_negative=all(e['polarity']=='explicit_negative' for e in inactive)
                findings.append({'id':rule.code+'_context','kind':'info' if is_negative else 'review',
                                 'title':'Отрицание условия' if is_negative else 'Неясная редакция/цитата',
                                 'explanation':('Найдена формулировка об отсутствии условия, не доказательство его наличия.'
                                                if is_negative else 'Цитата, условие или прежняя редакция: статус требует проверки.'),
                                 'next_action':'Проверить контекст и действующую редакцию по исходной странице.',
                                 'evidence':inactive})

    typed = extract_typed_fields(documents)
    terms = extract_terms(documents)
    # Textual date forms are a separate verified extractor, not a fallback guess.
    # Preserve the M02 typed field contract and ID provenance.
    deadline = terms['submission_deadline']
    if (typed['deadline']['status'] in ('not-found', 'ocr-required')
            and deadline['status'] == 'extracted'):
        td = typed['deadline']
        td.update(status='extracted', value=deadline['value'], unit='date',
                  confidence_basis='explicit_russian_date_with_submission_context',
                  evidence=[x['evidence'] for x in deadline['candidates']],
                  candidates=[dict(value=x['value'], unit=x['unit'], validity='parsed',
                                   reason='explicit_russian_date_with_submission_context',
                                   evidence=x['evidence']) for x in deadline['candidates']])
    work_span = terms['work_duration']
    if (typed['duration']['status'] in ('not-found', 'ocr-required')
            and work_span['status'] == 'extracted'):
        td = typed['duration']
        td.update(status='extracted', value=work_span['value'], unit=work_span['unit'],
                  confidence_basis='explicit_work_end_relative_duration',
                  evidence=[x['evidence'] for x in work_span['candidates']],
                  candidates=[dict(value=x['value'], unit=x['unit'], validity='parsed',
                                   reason='explicit_work_end_relative_duration',
                                   evidence=x['evidence']) for x in work_span['candidates']])
    advance_rows = advance_conditions(documents)
    conditions = advance_rows + clause_conditions(documents)
    conflicts = conflicts_for_review(advance_rows)
    conflicts.extend(additional_review_conflicts(conditions, typed))
    conflict_titles = {
        'advance_terms': ('advance_conflict', 'Возможное расхождение условий аванса между PDF',
                          'Разные действующие формулировки об авансе; юридическая сила не установлена.'),
        'sro_scope': ('sro_scope_review', 'Возможное расхождение по применимости СРО',
                      'Положительное и отрицательное требование могут относиться к разным видам работ.'),
        'duration_terms': ('duration_terms_review', 'Различающиеся сроки выполнения между PDF',
                           'Различаются указанные сроки или единицы измерения. Рабочие и календарные дни нельзя приравнивать автоматически.')}
    for c in reversed(conflicts):
        code, title, explanation = conflict_titles[c['family']]
        findings.insert(0, {'id': code, 'title': title, 'kind': 'risk',
                            'status':'needs-review', 'human_review_required': True,
                            'explanation': explanation, 'next_action': c['question'],
                            'evidence': c['evidence']})

    # Single canonical typed extraction for headline fields and lower audit.
    # Legacy field IDs stay unchanged for downstream readers.
    field_status = []
    map_typed = {'deadline':'deadline','budget':'budget_rub','duration':'duration'}
    for code, title, pattern in FIELDS:
        if code in map_typed:
            tf = typed[map_typed[code]]
            is_found = tf['status'] == 'extracted'
            evidence = tf['evidence'] if is_found else []
            field_value, field_unit = tf['value'], tf['unit']
            field_state = tf['status']
            if code == 'duration' and not is_found and terms['work_end_date']['status'] == 'extracted':
                # The date is a deadline, not the length of the work period.
                end = terms['work_end_date']
                evidence = [x['evidence'] for x in end['candidates']]
                field_value, field_unit, field_state, is_found = end['value'], 'work_end_date', 'extracted_end_date', True
            field_status.append({'id': code, 'title': title, 'found': is_found,
                                 'evidence': evidence, 'value': field_value,
                                 'unit': field_unit, 'status': field_state})
            continue
        if code == 'payment':
            # A clearly located advance/settlement clause counts as a *mention*
            # of payment conditions. We do not infer the entire payment schedule.
            evidence = evidence_from_pages(documents,
                r'(?:аванс\s+не\s+предусмотрен|аванс\s+\d{1,3}(?:[.,]\d+)?\s*%\s+предусмотрен|'
                r'оплата\s+после\s+при[её]мки|оплата[^.!?]{0,70}?в\s+течение\s+\d+\s+рабочих\s+дн)',
                max_per_document=1)
            payment = terms['payment_delay']
            if not evidence and payment['status'] == 'extracted':
                evidence = [x['evidence'] for x in payment['candidates']]
            field_status.append({'id': code, 'title': title,
                                 'found':bool(evidence), 'evidence': evidence[:3],
                                 'value': payment['value'] if payment['status']=='extracted' else None,
                                 'unit': payment['unit'] if payment['status']=='extracted' else None,
                                 'status':'mentioned' if evidence else 'not-found'})
            continue
        evidence = evidence_from_pages(documents, pattern, max_per_document=1)
        if code == 'scope' and not evidence and terms['scope']['status'] == 'extracted':
            evidence = [x['evidence'] for x in terms['scope']['candidates']]
        value = terms['scope']['value'] if code == 'scope' and terms['scope']['status']=='extracted' else None
        field_status.append({'id':code,'title':title,'found':bool(evidence),
                             'value': value, 'unit': None, 'evidence':evidence[:3]})

    issues = []
    for document in documents:
        for page in document['pages']:
            if not page['has_text']:
                issues.append(f'{document["file"]}, стр. {page["page"]}: нет извлекаемого текста, возможно нужен OCR (или страница пуста)')
    for field in field_status:
        if not field['found']:
            issues.append(f'{field["title"]}: не удалось извлечь по доступным шаблонам, проверьте вручную')
    for conflict in conflicts:
        issues.append(conflict['question'])
    recognized = [key for key, row in terms.items() if row['status'] in ('extracted', 'needs-review')]
    searchable_chars = sum(len(p['text']) for d in documents for p in d['pages'] if p['has_text'])
    # A parser success is not an extraction success. Very long real documents
    # with no extracted terms must never look like risk-free positive results.
    low_coverage = searchable_chars >= 2000 and len(recognized) == 0
    quality = {'status': ('no_searchable_text' if searchable_chars == 0 else
                           'insufficient_coverage' if low_coverage else 'limited_rule_coverage'),
               'text_characters': searchable_chars, 'term_categories_detected': len(recognized),
               'term_categories_total': len(terms), 'detected_categories': recognized,
               'validated_completeness': False,
               'message': ('Текст документа прочитан, но ни одно из контрольных условий не извлечено. '
                           'Нельзя делать вывод об отсутствии рисков.' if low_coverage else
                           'Найдены отдельные условия, полнота анализа документа не подтверждена.')}
    if low_coverage:
        issues.insert(0, 'Низкий охват: доступен текст PDF, но структурированные условия не извлечены.')
    if any(c['polarity']=='unclear' for c in advance_rows):
        issues.append('Сведения об авансе встречаются в контексте цитаты, условия или старой редакции: требуется ручная проверка.')

    return {
        'schema_version': SCHEMA_VERSION,
        'normalized_card': build_normalized_card(documents),
        'fast_dev2': build_domain_pipeline(documents),
        'typed_fields': typed,
        'terms': terms, 'analysis_quality': quality,
        'decision': 'ТРЕБУЕТСЯ РЕШЕНИЕ ЧЕЛОВЕКА',
        'documents': [{'file':d['file'],'page_count':d['page_count'],'sha256':d['sha256']} for d in documents],
        'findings':findings,
        'conditions':conditions,
        'conflicts':conflicts,
        'fields':field_status,
        'issues':issues,
        'stats':{'files':len(documents),'pages':sum(d['page_count'] for d in documents),
                 'findings':len(findings),'risks':sum(f['kind']=='risk' for f in findings),
                 'terms':len(recognized)},
        'disclaimer':'Демонстрационный эвристический анализ текста PDF. Формулировка не доказывает действующее юридическое условие. Статус UNKNOWN сохраняется при неопределённости. Не является юридическим заключением или решением об участии.',
    }


def analyze_folder(input_dir: Path, *, budget: ProcessingBudget | None = None,
                   cancelled=None) -> dict:
    budget = budget or ProcessingBudget()
    guard = RunGuard(budget, cancelled=cancelled)
    if not input_dir.is_dir():
        raise ValueError(f"Каталог не найден: {input_dir}")
    pdfs = sorted((x for x in input_dir.glob("*.pdf") if x.is_file() and not x.is_symlink()), key=lambda x: (x.name.casefold(), x.name))
    if not pdfs:
        raise ValueError("В каталоге нет PDF-файлов")
    if len(pdfs) > 50:
        raise ValueError("Для демо допускается максимум 50 PDF за запуск")
    documents = []
    errors = []
    for p in pdfs:
        try:
            if p.stat().st_size > budget.max_file_bytes:
                errors.append(f"{p.name}: pdf_file_byte_limit_exceeded")
                continue
            documents.append(extract_pdf(p, guard=guard))
        except ProcessingLimitError as e:
            errors.append(f"{p.name}: {e}")
            if str(e) in ('processing_cancelled','processing_time_budget_exceeded','batch_page_limit_exceeded'):
                break
        except (RuntimeError, ValueError, OSError) as e:
            errors.append(f"{p.name}: pdf_parse_error:{type(e).__name__}")
    # A failed intake is still represented honestly in the JSON/HTML/CSV:
    # unlike a bad input folder, these are discovered per-file parse failures.
    result = analyze(documents)
    # Layout evidence emitted separately in CLI as layout.json; not gold labels.
    result['layout'] = [
        {'file':d['file'], 'sha256':d['sha256'], 'page_count':d['page_count'],
         'document_role':d['document_role'], 'pages':d['pages']} for d in documents]
    result["issues"] = errors + result["issues"]
    structured_errors = []
    for error in errors:
        filename = error.split(':', 1)[0]
        code = error.split(': ',1)[1].split(':',1)[0] if ': ' in error else 'pdf_parse_error'
        if code == 'pdf_file_byte_limit_exceeded': code = 'file_too_large'
        structured_errors.append({'file': filename, 'code': code, 'message': error})
    if not documents:
        result['issues'].insert(0, 'Ни один входной PDF не прочитан; анализ не выполнен.')
        for field in result['typed_fields'].values():
            field['status'] = 'ambiguous'
            field['value'] = None
            field['confidence_basis'] = 'all_input_files_failed'
    return finalize(result, structured_errors, len(pdfs))
