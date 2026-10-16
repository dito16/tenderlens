"""Compact HTML table of FD2 *candidates*, with escaped untrusted PDF text."""
from html import escape


def render_fast_dev2(data):
    rows=[]
    for fact in data.get('facts',[]):
        ev=fact['evidence']
        items=[fact['kind'],fact.get('value'),fact.get('unit'),fact.get('review_required'),
               f"{ev['file']} (page {ev['page']})",ev['quote']]
        rows.append('<tr>'+''.join('<td>'+escape(str(x or ''))+'</td>' for x in items)+'</tr>')
    h="""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TenderLens FD2 candidates</title><style>body{font-family:system-ui,sans-serif;margin:30px;line-height:1.5}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:9px;border:1px solid #d4d4d4;text-align:left;vertical-align:top}tr:nth-child(2n){background:#f5f5f5}p{max-width:900px}</style></head><body><h1>TenderLens - проверяемые кандидаты FAST DEV 2</h1><p>Не юридическое заключение. Полнота и действующая редакция источников не подтверждены. UNKNOWN и needs-review требуют человека.</p><table><thead><tr><th>Поле</th><th>Значение</th><th>Единица</th><th>Проверка</th><th>Источник</th><th>Фрагмент</th></tr></thead><tbody>"""
    return h+''.join(rows)+'</tbody></table><p>Conflicts requiring human review: '+str(len(data.get('possible_conflicts',[])))+'</p></body></html>'
