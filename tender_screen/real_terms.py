"""Explicit, evidence-backed procurement clauses, separate from legal conclusions.

A small, deliberately scoped Russian clause extractor. It does not infer contract
priority, automatic obligations, or convert distinct time domains.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import re

MONTHS = {'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5,
          'июня': 6, 'июля': 7, 'августа': 8, 'сентября': 9,
          'октября': 10, 'ноября': 11, 'декабря': 12}
MONTH_WORD = '(?:' + '|'.join(MONTHS) + ')'
DATE_TOKEN = rf'(?P<value>\d{{1,2}}\s+{MONTH_WORD}\s+\d{{4}}\s*года?|\d{{1,2}}\.\d{{1,2}}\.\d{{4}})'
NUMBERS = {'одного': 1, 'один': 1, 'одной': 1, 'двух': 2, 'два': 2, 'две': 2,
           'трех': 3, 'трёх': 3, 'три': 3, 'четырех': 4, 'четырёх': 4, 'четыре': 4,
           'пяти': 5, 'пять': 5, 'шести': 6, 'шесть': 6, 'семи': 7, 'семь': 7,
           'восьми': 8, 'восемь': 8, 'девяти': 9, 'девять': 9,
           'десяти': 10, 'десять': 10, 'двенадцати': 12}
N = r'(?:\d{1,3}(?:\s*\(\s*[а-яё]+(?:\s+[а-яё]+){0,2}\s*\))?|(?:одного|один|одной|двух|два|две|трех|трёх|три|четырех|четырёх|четыре|пяти|пять|шести|шесть|семи|семь|восьми|восемь|девяти|девять|десяти|десять|двенадцати))'


@dataclass(frozen=True)
class Spec:
    key: str
    title: str
    pattern: str
    value_type: str
    max_per_document: int = 3


SPECS = (
    Spec('submission_deadline', 'Подача предложения',
         rf'(?:просим\s+направить|срок\s+(?:подачи|при[её]ма)\s+(?:заявок|предложений)|'
         rf'при[её]м\s+(?:заявок|предложений)|подача\s+(?:заявок|предложений))'
         rf'[^!?]{{0,210}}?\b(?:до|по)\s*(?:\d{{1,2}}:\d{{2}}[^!?]{{0,45}}?)?{DATE_TOKEN}', 'date'),
    Spec('work_start_offset', 'Начало выполнения после события',
         rf'начальн\w*\s+срок\s*:\s*через\s+(?P<value>{N})\s+(?P<unit>рабочих|календарных)\s+дн(?:ей|я)', 'days'),
    Spec('work_duration', 'Продолжительность работ',
         rf'(?:конечн\w*\s+срок|срок\s+выполнения\s+работ|срок\s+проведения\s+работ)'
         rf'[^.!?]{{0,60}}?(?:не\s+более\s+|составляет\s+|в\s+течение\s+)?'
         rf'(?P<value>{N})\s+(?P<unit>рабочих|календарных)?\s*(?P<kind>дн(?:ей|я)|месяц(?:ев|а|ы)?)\b', 'duration'),
    Spec('work_end_date', 'Дата окончания работ',
         rf'(?:срок\s+выполнения\s+работ|срок\s+выполнения|конечн\w*\s+срок|'
         rf'с\s+даты\s+подписания\s+договора)[^.!?]{{0,65}}?\bдо\s+{DATE_TOKEN}', 'date'),
    Spec('payment_delay', 'Срок оплаты после приёмки',
         rf'\bоплат[аыуе]\b[^.!?]{{0,220}}?\b(?:в\s+течени[еи]|в\s+срок\s+не\s+более|не\s+позднее|через)'
         rf'\s+(?P<value>{N})\s+(?P<unit>рабочих|календарных)?\s*дн(?:ей|я|ь)', 'days'),
    Spec('site_visit', 'Осмотр объекта до предложения',
         r'(?:перед\s+подачей\s+коммерческого\s+предложения|до\s+подачи\s+предложения)'
         r'[^.!?]{0,105}?(?:осмотр\w*|осмотр\s+объекта)', 'presence'),
    Spec('warranty', 'Гарантийный срок',
         rf'гарантийн\w*\s+срок\b[^.!?]{{0,110}}?(?:составляет|устанавливается\s+в\s+размере|на\s+срок)\s+'
         rf'(?P<value>{N})\s+(?P<unit>месяц(?:ев|а|ы)?|лет|года|год)', 'duration'),
    Spec('request_start_sla', 'Начало работ по заявке',
         rf'исполнитель\s+в\s+течение\s+(?P<value>{N})\s+(?P<unit>рабочих|календарных)\s+дн(?:ей|я)'
         rf'[^.!?]{{0,105}}?приступает\s+к\s+(?:ремонтным\s+)?работам', 'days'),
    Spec('request_completion_sla', 'Завершение работ по заявке',
         rf'(?:выполнить\s+ремонтн\w*\s+работы|выполнени\w*\s+работ)\b[^.!?]{{0,125}}?'
         rf'не\s+позднее\s+(?P<value>{N})\s+(?P<unit>рабочих|календарных)\s+дн(?:ей|я)'
         rf'\s+после\s+получения\s+заявки', 'days'),
    Spec('scope', 'Предмет закупки',
         r'(?:наименование(?:\s+закупки)?|предмет\s+договора)\s*'
         r'(?P<value>выполнени[ея]\s+работ\s+по\s+[^.!?]{8,95}?)'
         r'(?=\s+(?:способ\s+|содержание\s+|место\s+|помещения\s+|наименование\s+|предмет\s+|закупка\s+)|$)', 'text'),
    Spec('sro_requirement', 'Требование СРО',
         r'(?:допуск[аиов]*\s+саморегулируемой\s+организаци\w*\s*\(СРО\)|'
         r'членств\w*\s+в\s+СРО\s+требу\w*|\bСРО\s+требу\w*)', 'presence'),
    Spec('ks_acceptance', 'Приёмка КС-2 / КС-3',
         r'\bКС\s*[-–]\s*2\b[^.!?]{0,170}?\bКС\s*[-–]\s*3\b', 'presence'),
)


def _parse_date(raw: str) -> str | None:
    norm = re.sub(r'\s+', ' ', raw.strip().lower())
    try:
        if '.' in norm and re.fullmatch(r'\d{1,2}\.\d{1,2}\.\d{4}', norm):
            dd, mm, yyyy = map(int, norm.split('.'))
        else:
            mat = re.fullmatch(r'(\d{1,2})\s+([а-яё]+)\s+(\d{4})\s*(?:года|год)?', norm)
            if mat is None or mat[2] not in MONTHS:
                return None
            dd, mm, yyyy = int(mat[1]), MONTHS[mat[2]], int(mat[3])
        if not 2000 <= yyyy <= 2100:
            return None
        return date(yyyy, mm, dd).isoformat()
    except ValueError:
        return None


def _number(raw: str) -> int | None:
    mat = re.match(r'\s*(\d{1,3})', raw)
    if mat:
        return int(mat[1])
    return NUMBERS.get(raw.lower().strip())


def _value(spec: Spec, mat: re.Match) -> tuple[str | None, str | None]:
    if spec.value_type == 'presence':
        return 'mentioned', 'wording'
    raw = mat.group('value')
    if spec.value_type == 'text':
        return re.sub(r'(?<=мастер-)\s*закупки\s+', ' ', raw.strip(' ,.;'), flags=re.I), 'text'
    if spec.value_type == 'date':
        return _parse_date(raw), 'date'
    val = _number(raw)
    if val is None or val <= 0 or val > 3650:
        return None, None
    unit = (mat.groupdict().get('unit') or '').lower()
    if spec.key in {'work_duration'}:
        kind = mat.groupdict().get('kind') or ''
        if kind.startswith('месяц'):
            return str(val), 'months'
    if spec.key == 'warranty':
        return str(val), 'months' if unit.startswith('месяц') else 'years'
    return str(val), 'work_days' if unit == 'рабочих' else 'calendar_days' if unit == 'календарных' else 'days_unspecified'



# R4: These are wording *candidates*, never proof of a legal obligation.
# Scope and contract-end dates may be rendered before their labels by PyMuPDF
# in two-column procurement tables. Do not turn an arbitrary date or service
# mention into a result without an identifiable procurement-field anchor.
DATE_BODY = rf'(?:\d{{1,2}}\s+{MONTH_WORD}\s+\d{{4}}\s*(?:года|год)?|\d{{1,2}}\.\d{{1,2}}\.\d{{4}})'
DATE_VALUE = rf'(?P<value>{DATE_BODY})'
DATE_CONTEXT = (r'(?:срок\s+(?:выполнения|оказания|поставки|предоставления)'
                r'(?:\s+(?:работ|услуг|товара|товаров))?|'
                r'окончани[ея]\s+(?:выполнения\s+)?работ|'
                r'конечн\w*\s+срок)')

R4_EXTRA_PATTERNS = {
    'work_end_date': (
        # Example: "Срок поставки товара: с 12 января по 30 декабря 2026 года".
        rf'\b{DATE_CONTEXT}\b[^;!?]{{0,125}}?\b(?:до|по|не\s+позднее)\s+{DATE_VALUE}',
        # Example: "С 01.01.2026 по 31.12.2026 Срок оказания услуг".
        rf'\bс\s+{DATE_BODY}\s+по\s+{DATE_VALUE}\s+{DATE_CONTEXT}\b',
        # Example: "окончание выполнения работ: не позднее 17.11.2025 г.".
        rf'\bокончани[ея]\s+(?:выполнения\s+)?работ\s*[:–-]?\s*(?:не\s+позднее|до|по)\s+{DATE_VALUE}',
    ),
    'warranty': (
        # Keep the number in the warranty clause, not a later unrelated duration.
        rf'\bгаранти[яи]\s+на\s+[^.!?]{{3,75}}?\s*[:–-]\s*'
        rf'(?P<value>{N})\s+(?P<unit>месяц(?:ев|а|ы)?|лет|года|год)\b',
        # Example: "Гарантийный Не менее 12 месяцев срок" (table reading order).
        rf'\bгарантийн\w*\s+(?:не\s+менее\s+)?(?P<value>{N})\s+'
        rf'(?P<unit>месяц(?:ев|а|ы)?|лет|года|год)\s+срок\b',
        # Example: "Гарантийный срок на работы ... и составляет 36 месяцев".
        rf'\bгарантийн\w*\s+срок\b[^.!?]{{0,190}}?\b'
        rf'(?:составляет|устанавливается\s+в\s+размере|не\s+менее|равен)\s+'
        rf'(?P<value>{N})\s+(?P<unit>месяц(?:ев|а|ы)?|лет|года|год)\b',
        # Example: "Гарантийный срок: не менее 12 месяцев".
        rf'\bгарантийн\w*\s+срок\s*[:–-]\s*(?:не\s+менее\s+)?'
        rf'(?P<value>{N})\s+(?P<unit>месяц(?:ев|а|ы)?|лет|года|год)\b',
    ),
    'request_completion_sla': (
        # Example: "Срок оказания 10 рабочих дней с момента принятия Заявки".
        rf'\bсрок\s+(?:оказания\s+(?:услуг\s+)?|поставки\s+(?:товара\s+)?|'
        rf'выполнения\s+(?:работ\s+)?)\s*[:–-]?\s*'
        rf'(?:не\s+более\s+|составляет\s+|в\s+течение\s+)?'
        rf'(?P<value>{N})\s+(?P<unit>рабочих|календарных)\s+дн(?:ей|я)\b'
        rf'[^.!?]{{0,115}}?\b(?:заявк\w*|заказ\w*)\b',
        # Example: "Срок поставки товара составляет три рабочих дня со дня получения заявки".
        rf'\bсрок\s+(?:оказания\s+(?:услуг\s+)?|поставки\s+(?:товара\s+)?|'
        rf'выполнения\s+(?:работ\s+)?)\s*[:–-]?\s*составляет\s+'
        rf'(?P<value>{N})\s+(?P<unit>рабочих|календарных)\s+дн(?:ей|я)\b'
        rf'[^.!?]{{0,115}}?\bзаявк\w*\b',
    ),
}

# Layout markers are extracted from the same normalized, 1-based PDF page text.
_SCOPE_PHRASE = re.compile(
    r'\b(?P<value>(?:на\s+)?(?:выполнени[ея]\s+работ(?:\s+по)?|'
    r'оказани[ея]\s+услуг|поставк[ауи]\s+товар\w*)\b)', re.I)
_SCOPE_LABEL = re.compile(r'\bнаименование\b', re.I)
_SCOPE_STOP = re.compile(r'\b(?:закупки\s+способ|способ\s+(?:проведения|закупки)|'
                         r'способ\b|ИКЗ\s+\d{4,}|место\s+(?:оказания|поставки)|'
                         r'содержание\s+и\s+об[ъь]ем)', re.I)
_SCOPE_NOISE = re.compile(r'\b(?:наименование|закупки)\b', re.I)


def _scope_hits(text: str) -> list[tuple[int, int, str, str]]:
    """High-precision subject phrases in heading or procurement-name table.

    Scan a short region around the official name label, not service-related
    phrases in the body. Keep a contiguous source span for evidence even if
    the PDF's reading order inserts a table header into the phrase.
    """
    hits = []
    for m in _SCOPE_PHRASE.finditer(text):
        before = text[max(0, m.start()-105):m.start()]
        after = text[m.end():m.end()+115]
        labeled = bool(_SCOPE_LABEL.search(before) or _SCOPE_LABEL.search(after))
        contract_title = (m.start() <= 300 and
                          bool(re.search(r'\b(?:контракт|договор)\b', text[:m.start()], re.I)))
        contract_subject = bool(re.search(r'\bпредмет\s+контракт\w*\b', before, re.I))
        if not (labeled or contract_title or contract_subject):
            continue
        # On an invitation, require the heading region; on contracts the
        # introductory title/subject is enough. Never guess from a later list.
        if m.start() > 1600 and not contract_subject:
            continue
        upper = min(len(text), m.end()+230)
        nxt = _SCOPE_STOP.search(text, m.end(), upper)
        end = nxt.start() if nxt else min(upper, len(text))
        piece = text[m.start():end]
        # Two-column extraction may put 'Наименование' and 'закупки' in
        # the middle of the value; remove only those table labels.
        clean = _SCOPE_NOISE.sub(' ', piece)
        clean = re.sub(r'\s+', ' ', clean).strip(' ,;:.–-')
        # A heading must contain actual words beyond 'выполнение работ'.
        if len(clean) < 13 or len(clean) > 250 or not re.search(r'[а-яё]{3,}', clean[9:], re.I):
            continue
        # Avoid a trailing fragment if the parser never saw an actual stop.
        if nxt is None and end < len(text):
            continue
        hits.append((m.start(), end, clean, 'text'))
        break  # One document-level subject is not a confidence vote.
    return hits


def _r4_hits(spec: Spec, text: str) -> list[tuple[int, int, str, str]]:
    if spec.key == 'scope':
        scoped = _scope_hits(text)
        if scoped:
            return scoped
    patterns = [spec.pattern, *R4_EXTRA_PATTERNS.get(spec.key, ())]
    hits = []
    seen = set()
    for pattern in patterns:
        for mat in re.compile(pattern, re.I).finditer(text):
            # Never bridge a completed sentence to borrow a later date.
            # Dots *inside* DD.MM.YYYY are decimal-like separators, not stops.
            if (spec.key == 'work_end_date'
                    and re.search(r'(?<!\d)[.!?](?!\d)', mat.group(0))):
                continue
            value, unit = _value(spec, mat)
            if value is None:
                continue
            # Avoid two variants of the same phrase producing duplicate proofs.
            start, end = mat.span()
            ident = (value, unit, start)
            if ident in seen:
                continue
            seen.add(ident)
            hits.append((start, end, value, unit))
    hits.sort(key=lambda entry: (entry[0], entry[1]))
    return hits


def extract_terms(documents: list[dict]) -> dict:
    """Produce conservative per-category evidence, with no cross-scope merging."""
    result = {}
    for spec in SPECS:
        found = []
        for doc in documents:
            count = 0
            for page in doc['pages']:
                t = page['text']
                for start, end, value, unit in _r4_hits(spec, t):
                    token = f"{doc['sha256']}|{page['page']}|{spec.key}|{start}|{end}".encode()
                    found.append({'value': value, 'unit': unit,
                                  'evidence': {'id': 'RT-' + hashlib.sha256(token).hexdigest()[:20],
                                               'file': doc['file'], 'source_sha256': doc['sha256'],
                                               'page': page['page'], 'match': t[start:end],
                                               'normalized_span': [start, end],
                                               'span_basis': 'normalized_page_text',
                                               'quote': t[max(0,start-80): min(len(t),end+85)]}})
                    count += 1
                    if count >= (1 if spec.key == 'scope' else spec.max_per_document):
                        break
                if count >= (1 if spec.key == 'scope' else spec.max_per_document):
                    break
        combinations = {(x['value'], x['unit']) for x in found}
        status = 'not-found' if not found else 'extracted' if len(combinations)==1 else 'needs-review'
        result[spec.key] = {'title': spec.title, 'status': status,
                            'value': found[0]['value'] if status == 'extracted' else None,
                            'unit': found[0]['unit'] if status == 'extracted' else None,
                            'candidates': found,
                            'evidence_ids': [x['evidence']['id'] for x in found]}
    return result
