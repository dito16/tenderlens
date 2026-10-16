"""Static, offline HTML report and evidence CSV. User input is HTML-escaped."""
from __future__ import annotations
import csv
import re
from html import escape as esc
from pathlib import Path


def _evidence(entries: list[dict]) -> str:
    return "".join(
        '<div class="evidence"><div class="source">'
        f'{esc(x["file"])} · стр. {x["page"]}</div>'
        f'<div class="quote">{esc(x["quote"])}</div>'
        f'<div class="code">Evidence ID: {esc(str(x.get("id", "legacy-unlinked")))}</div></div>'
        for x in entries
    )


def render_html(result: dict) -> str:
    stats = result["stats"]
    def field_text(field: dict) -> str:
        if field.get('value') is not None:
            return str(field['value']) + (' ' + str(field['unit']) if field.get('unit') else '')
        return str(field['evidence'][0]['match']) if field.get('evidence') else 'Нужна ручная проверка'

    def field_status_label(field: dict) -> str:
        if field.get('found'):
            return 'НАЙДЕНО'
        return {'ambiguous': 'НЕОДНОЗНАЧНО', 'ocr-required': 'НУЖЕН OCR'}.get(
            field.get('status'), 'НЕ ИЗВЛЕЧЕНО')

    field_rows = "".join(
        f'<div class="field"><div><strong>{esc(f["title"])}</strong>'
        f'<div class="field-source">{esc(field_text(f))}</div></div>'
        f'<span class="tag {"ok" if f["found"] else "missing"}">{field_status_label(f)}</span></div>'
        for f in result["fields"]
    )
    blocks = []
    for f in result["findings"]:
        kind = {"risk": "РИСК / СВЕРИТЬ", "review": "ПРОВЕРИТЬ", "requirement": "УСЛОВИЕ", "info": "КОНТЕКСТ"}[f["kind"]]
        blocks.append(
            f'<article class="finding {f["kind"]}"><div class="finding-top">'
            f'<span class="tag {f["kind"]}">{kind}</span><span class="code">{esc(f["id"])}</span></div>'
            f'<h3>{esc(f["title"])}</h3><p>{esc(f["explanation"])}</p>'
            f'<div class="action"><b>Дальше:</b> {esc(f["next_action"])}</div>'
            + _evidence(f["evidence"]) + '</article>'
        )
    # An explicitly labeled audit strip prevents a partial result from being
    # mistaken for a complete scan. All new values are escaped before HTML.
    status = result.get('processing_status', 'legacy-unknown')
    err_rows = ''.join(
        f'<li>{esc(str(e.get("file", "")))}: {esc(str(e.get("code", "")))}</li>'
        for e in result.get('errors', []))
    typed_rows = ''.join(
        '<li><b>' + esc(str(name)) + '</b>: '
        + esc(str(f.get('status', 'unknown'))) + ' / '
        + esc(str(f.get('value') if f.get('value') is not None else 'UNKNOWN'))
        + ' ' + esc(str(f.get('unit') or ''))
        + ' | ' + ', '.join(esc(str(x)) for x in f.get('evidence_ids', []))
        + '</li>' for name, f in result.get('typed_fields', {}).items())
    quality = result.get('analysis_quality', {})
    term_rows = []
    for key, term in result.get('terms', {}).items():
        if term['status'] == 'not-found':
            continue
        candidates = term.get('candidates', [])
        if term['status'] == 'extracted':
            detail = str(term.get('value') or '') + ' ' + str(term.get('unit') or '')
        else:
            detail = 'ТРЕБУЕТСЯ СВЕРКА (различные значения)'
        term_rows.append('<article class="finding"><div class="finding-top"><strong>'
                         + esc(str(term['title'])) + '</strong><span class="code">'
                         + esc(key) + '</span></div><p>' + esc(detail) + '</p>'
                         + _evidence([x['evidence'] for x in candidates]) + '</article>')
    quality_panel = ('<section class="panel" id="coverage"><h2>Охват анализа</h2>'
                     '<p><b>' + esc(str(quality.get('status', 'не оценивался'))) + '</b>. '
                     + esc(str(quality.get('message', ''))) + '</p>'
                     '<p>Найдено категорий условий: ' + esc(str(quality.get('term_categories_detected', 0)))
                     + ' из ' + esc(str(quality.get('term_categories_total', 0))) +
                     '. Текстовых символов: ' + esc(str(quality.get('text_characters', 0))) +
                     '. Полнота анализа НЕ подтверждена.</p></section>')
    terms_panel = ('<section class="panel" id="structured-terms"><h2>Структурированные условия с доказательствами</h2>'
                   '<p class="hint">Тип события и сроки не смешиваются. Каждое значение - кандидат для ручной проверки.</p>'
                   + (''.join(term_rows) if term_rows else '<p>Не извлечено ни одного условия.</p>') + '</section>')
    conflict_rows = ''.join(
        '<li>' + esc(str(c.get('family'))) + ': '
        + esc(str(c.get('status'))) + ' ['
        + ', '.join(esc(str(x)) for x in c.get('evidence_ids', [])) + ']</li>'
        for c in result.get('conflicts', []))
    audit_panel = (
        '<section class="panel" id="audit-contract">'
        '<h2>Статус обработки и проверяемые ссылки</h2>'
        '<p><b>processing_status: ' + esc(status) + '</b> | schema_version: '
        + esc(str(result.get('schema_version', 'legacy'))) + '</p>'
        '<p>Сведения об отсутствии условия не означают проверку его применимости.</p>'
        '<h3>Типизированные поля</h3><ul>' + (typed_rows or '<li>Нет данных</li>') + '</ul>'
        '<h3>Возможные противоречия</h3><ul>'
        + (conflict_rows or '<li>Не обнаружены по реализованным правилам</li>') + '</ul>'
        '<h3>Ошибки чтения отдельных PDF</h3><ul>'
        + (err_rows or '<li>Не зафиксированы</li>') + '</ul>'
        '<p>Полный реестр ID, SHA256, страниц и цитат: analysis.json и evidence.csv.</p>'
        '</section>')
    card = result.get('normalized_card') or {}
    card_rows=[]
    for label,key in [('Предмет закупки','subject'),('НМЦК, руб.','budget_rub')]:
        fld=card.get(key) or {}
        value=fld.get('value')
        card_rows.append('<div class="field"><div><strong>'+esc(label)+'</strong><div class="field-source">'+
            esc(str(value) if value is not None else 'НЕТ ДОСТОВЕРНОГО ЗНАЧЕНИЯ')+
            '</div></div><span class="tag">'+esc(str(fld.get('status','unknown')))+'</span></div>')
    card_panel = ('<section class="panel"><h2>Нормализованная карточка (FAST DEV)</h2>'
                  + ''.join(card_rows)
                  + '<p class="hint">Кандидаты, источники и причины отказа: subject_price.json. '
                  + 'Ничего не подтверждает юридическую применимость условий.</p></section>')
    doc_rows = "".join(f'<li>{esc(d["file"])} <span>{d["page_count"]} стр.</span></li>' for d in result["documents"])
    issue_rows = "".join(f'<li>{esc(s)}</li>' for s in result["issues"]) or '<li>Все базовые поля найдены по шаблонам. Проверка человеком всё равно требуется.</li>'
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TenderLens · проверка тендерного комплекта</title>
<style>
:root{{--ink:#172b35;--muted:#60717b;--bg:#f4f7f8;--teal:#09796e;--border:#dae4e6;--gold:#f3ad49}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.52 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}}
header{{background:#102f3a;color:#fff;padding:35px 0 36px}}.container{{max-width:1100px;margin:auto;padding:0 28px}}
.eyebrow{{font-size:11px;letter-spacing:.19em;text-transform:uppercase;color:#82d6ca;font-weight:800}}h1{{font-size:35px;letter-spacing:-1px;margin:7px 0 6px}}.lead{{color:#b7cbd1;margin:0;max-width:760px}}
.stat-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-top:24px}}
.stat{{background:#20454f;border:1px solid #315b65;border-radius:11px;padding:12px 17px}}.stat b{{display:block;font-size:26px;color:#fff}}.stat small{{color:#c4d3d6}}
main{{padding:30px 0 55px}}.banner{{border-left:5px solid var(--gold);background:#fff5e5;padding:17px 21px;border-radius:7px;margin-bottom:23px;line-height:1.45}}
.columns{{display:grid;grid-template-columns:1.04fr 1.96fr;gap:24px;align-items:start}}
.panel{{background:#fff;border:1px solid var(--border);box-shadow:0 2px 7px #20343b06;border-radius:11px;padding:20px;margin-bottom:20px}}
h2{{font-size:20px;margin:0 0 15px}}h3{{font-size:18px;margin:7px 0}}.hint{{color:var(--muted);font-size:13px;margin-top:-6px}}
.field{{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:10px 0;border-top:1px solid #e7edef}}
.field-source{{color:var(--muted);font-size:12px;margin-top:2px;max-width:275px;overflow-wrap:anywhere}}
.tag{{font-size:10px;letter-spacing:.06em;font-weight:800;white-space:nowrap;border-radius:5px;padding:5px 7px;background:#eaf1f2;color:#3e6468}}
.tag.ok{{color:#046a60;background:#e3f4f0}}.tag.missing{{color:#8a5a14;background:#fff0d7}}
.tag.risk{{background:#ffe9e4;color:#b13c25}}.tag.review{{background:#fff0d7;color:#915a10}}.tag.requirement{{background:#e6eefb;color:#355a94}}.tag.info{{background:#e6f4ed;color:#306a4c}}
.finding{{border:1px solid var(--border);border-left:4px solid #bccccc;border-radius:8px;background:#fff;padding:18px;margin:12px 0}}
.finding.risk{{border-left-color:#dc6545}}.finding.review{{border-left-color:#e8b14e}}.finding.requirement{{border-left-color:#5778b8}}
.finding-top{{display:flex;justify-content:space-between;align-items:center}}.code{{color:#8a979e;font:11px monospace}}.finding p{{margin:5px 0 12px;color:#526874}}
.action{{background:#f4f8f9;padding:10px 12px;border-radius:6px;font-size:13px;margin-bottom:12px}}
.evidence{{border-top:1px solid #e2e9eb;padding-top:10px;margin-top:10px}}.source{{font-weight:750;font-size:12px;color:#11786f;margin-bottom:4px}}
.quote{{font-size:13px;color:#394e59;overflow-wrap:anywhere}}ul{{padding-left:18px}}li{{margin:6px 0}}.docs li{{list-style:square;overflow-wrap:anywhere}}
.docs li span{{font-size:12px;color:#73868f}}footer{{font-size:12px;color:#71848b;margin-top:25px;border-top:1px solid #d7e1e3;padding-top:17px}}
@media(max-width:800px){{.columns{{grid-template-columns:1fr}}.stat-row{{grid-template-columns:repeat(2,1fr)}}h1{{font-size:29px}}}}
@media print{{body{{background:#fff}}.container{{max-width:none}}.columns{{display:block}}.finding{{break-inside:avoid}}header{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
</style></head>
<body><header><div class="container"><div class="eyebrow">TenderLens / Offline screening demo</div><h1>Карточка проверки тендерного комплекта</h1>
<p class="lead">Первичный разбор PDF с подтверждающими цитатами. Только локальные файлы. Никаких внешних запросов и автоматического решения об участии.</p>
<div class="stat-row"><div class="stat"><b>{stats["files"]}</b><small>PDF-документа</small></div><div class="stat"><b>{stats["pages"]}</b><small>Страниц</small></div><div class="stat"><b>{stats["findings"]}</b><small>Сигналов</small></div><div class="stat"><b>{stats["risks"]}</b><small>Требуют сверки</small></div><div class="stat"><b>{stats.get("terms",0)}</b><small>Категорий условий</small></div></div></div></header>
<main><div class="container"><div class="banner"><b>{esc(result["decision"])}</b><br>{esc(result["disclaimer"])}</div>
{card_panel}{quality_panel}{terms_panel}<div class="columns"><aside><section class="panel"><h2>Основные поля</h2><p class="hint">Найдено по текстовым шаблонам, не верифицировано.</p>{field_rows}</section>
<section class="panel"><h2>Вопросы к проверке</h2><ul>{issue_rows}</ul></section>
<section class="panel"><h2>Проверенные файлы</h2><ul class="docs">{doc_rows}</ul></section></aside>
<section class="panel"><h2>Найденные сигналы и выдержки</h2><p class="hint">Для каждого сигнала показано исходное место в файле. Сигнал может оказаться неприменимым: нужен контекст.</p>{''.join(blocks) if blocks else '<p>Совпадений не найдено. Это не означает отсутствие рисков.</p>'}</section></div>{audit_panel}
<footer>TenderLens · Realistic audit repair R1 · Offline portfolio demo · No network · No legal opinion · Human-in-the-loop</footer></div></main></body></html>'''



def _spreadsheet_text(value: object) -> str:
    """Best-effort spreadsheet-text protection; JSON keeps the raw evidence.

    OWASP notes there is no universal Excel/CSV formula defense. For this
    human-readable register, replace CR/LF and prefix dangerous strings with
    a tab in a QUOTE_ALL cell; callers must not treat this as raw evidence.
    """
    text = str(value if value is not None else '')
    text = text.replace('\r', ' ').replace('\n', ' ')
    probe = text.lstrip(' \t\ufeff')
    if (probe.startswith(('=', '+', '-', '@', '＝', '＋', '－', '＠'))
            or text.startswith(('\t', '\ufeff'))):
        return '\t' + text
    return text


def write_csv(result: dict, path: Path) -> None:
    """A registry export, one row per unique proof, not duplicated findings."""
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file, delimiter=';', quoting=csv.QUOTE_ALL)
        writer.writerow(['Evidence ID', 'Код ссылки', 'Документ', 'SHA256', 'Страница',
                         'Цитата', 'Совпадение', 'Диапазон', 'Основание диапазона',
                         'Статус обработки'])
        for ev in result.get('evidence', []):
            fields = [ev.get('id',''), ', '.join(ev.get('references', [])),
                      ev.get('file',''), ev.get('source_sha256',''),
                      ev.get('page',''), ev.get('quote',''), ev.get('match',''),
                      str(ev.get('normalized_span','')),
                      ev.get('span_basis',''), result.get('processing_status','unknown')]
            writer.writerow([_spreadsheet_text(v) for v in fields])
