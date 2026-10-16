"""M03.1-M03.3: conservative, evidence-first money and subject candidates.

No ML, no inference from penalties/security to an award budget; no OCR.
A candidate is not a legal verification. Outputs retain Decimal as a string.
"""
from __future__ import annotations
import hashlib
import re
from decimal import Decimal, InvalidOperation
from .pdf_layout import span_bbox

# Labels must be explicit; neighbouring numbers cannot be silently borrowed.
ROLE_PATTERNS = (
    ('initial_maximum', re.compile(r'(?i)(?:\bНМЦК\b|\bНМЦД\b|начальн\w*\s*\(?максимальн\w*\)?\s+цен\w*)')),
    ('budget_limit', re.compile(r'(?i)\b(?:лимит\s+(?:финансирования|бюджета)|предельн\w*\s+стоимост\w*)\b')),
    ('bid_security', re.compile(r'(?i)\bобеспечени\w*\s+заявк\w*\b')),
    ('performance_security', re.compile(r'(?i)\bобеспечени\w*\s+исполнени\w*\s+(?:договора|контракта)\b')),
    ('penalty', re.compile(r'(?i)\b(?:штраф\w*|пен[ия]|неустойк\w*)\b')),
    ('contract_price', re.compile(r'(?i)\b(?:цена|стоимость|сумма)\s+(?:договора|контракта|работ|поставки)\b')),
)
MONEY = re.compile(r'(?<!\d)(?P<amount>(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?|\d{1,12}(?:[.,]\d{1,2})?))'
    r'\s*(?P<currency>руб(?:лей|ля|\.|\b)|₽|RUB\b)', re.I)
WORDS = re.compile(r'(?i)\b(?:ноль|один|одна|два|две|три|четыре|пять|шесть|семь|восемь|девять|'
                   r'десять|двадцать|тридцать|сорок|пятьдесят|сто|тысяч[аи]?|миллион\w*)'
                   r'(?:\s+\w+){0,6}\s+руб(?:лей|ля|\.)?')

SUBJECT = re.compile(r'(?i)(?<!\w)(?:наименование\s+(?:объекта\s+)?закупки|'
                     r'предмет\s+(?:договора|контракта|закупки)|объект\s+закупки)\s*[:\-–]\s*')
OBLIGATION = re.compile(r'(?i)\b(?:подрядчик|исполнитель|поставщик)\s+обязуется\s+'
                        r'(?:выполнить|оказать|поставить)\s+')
STOP = re.compile(r'(?i)\b(?:начальн\w*\s+максимальн\w*\s+цен\w*|'
                  r'условия\s+оплаты|обеспечени\w*\s+заявк\w*|'
                  r'срок\s+(?:выполнения|поставки)|способ\s+(?:закупки|проведения)|'
                  r'техническое\s+задание|приложение\s+\d+|раздел\s+\d+)\b')
BAD_SUBJECT = re.compile(r'(?i)^(?:техническое\s+задание|условия\s+оплаты|'
                         r'общие\s+положения|проект\s+договора|приложение|'
                         r'закупочная\s+документация)\b')


def _evidence(doc, page, start, end, field):
    text = page.get('text') or ''
    token=f"{doc['sha256']}|{page['page']}|{field}|{start}|{end}"
    box=span_bbox(page, start, end)
    return {'id':'FD-'+hashlib.sha256(token.encode()).hexdigest()[:18],
            'file':doc['file'], 'source_sha256':doc['sha256'], 'page':page['page'],
            'normalized_span':[start,end], 'match':text[start:end],
            'quote':text[max(0,start-50):min(len(text),end+70)],
            'bbox':box, 'bbox_status':'verified_words' if box is not None else 'unavailable',
            'span_basis':'normalized_page_text'}


def parse_rub_amount(raw: str):
    """Return normalized Decimal string or an explicit rejection reason."""
    m=MONEY.fullmatch(raw.strip())
    if not m:
        return None,'not_a_numeric_rub_amount'
    s=re.sub(r'[\s\u00a0\u202f]','',m.group('amount')).replace(',','.')
    try:
        value=Decimal(s)
    except InvalidOperation:
        return None,'invalid_decimal'
    if not value.is_finite() or value <= 0:
        return None,'not_positive'
    if value.as_tuple().exponent < -2:
        return None,'overprecision'
    return f'{value:.2f}', 'valid_rub_decimal'


def _money_for_page(doc,page):
    t=page.get('text') or ''
    labels=[]
    for role, expr in ROLE_PATTERNS:
        for hit in expr.finditer(t):
            labels.append((hit.start(),hit.end(),role,hit.group(0)))
    labels.sort(key=lambda r:r[0])
    rows=[]
    for idx,(begin,end,role,label) in enumerate(labels):
        next_label = labels[idx+1][0] if idx+1 < len(labels) else len(t)
        # Do not borrow amounts from other sections or another sentence.
        segment=t[end:min(end+115,next_label)]
        boundary=re.search(r'[;!?]|\.(?=\s+[А-ЯA-Z])',segment)
        if boundary: segment=segment[:boundary.start()]
        # Ignore '№ 12' and percentages: no explicit RUB amount => no numeric value.
        candidates=list(MONEY.finditer(segment))
        chosen=candidates[0] if candidates else None
        if chosen:
            a,b=end+chosen.start(),end+chosen.end()
            val,reason=parse_rub_amount(t[a:b])
            context=t[max(0,begin-20):min(len(t),b+30)]
            conditional=bool(re.search(r'(?i)\b(?:ориентировочно|примерно|не\s+более|до)\b',t[end:a]))
            rows.append({'role':role, 'value':val, 'currency':'RUB',
                         'validity':'needs-review' if conditional else ('parsed' if val else 'rejected'),
                         'reason':'conditional_amount' if conditional else reason,
                         'context':context,'evidence':_evidence(doc,page,begin,b,'money:'+role)})
        elif WORDS.search(segment):
            m=WORDS.search(segment)
            rows.append({'role':role, 'value':None, 'currency':'RUB',
                         'validity':'needs-review', 'reason':'amount_in_words_not_parsed',
                         'context':t[begin:min(len(t),end+len(segment))],
                         'evidence':_evidence(doc,page,begin,end+m.end(),'money_words:'+role)})
    return rows


def _subjects_for_page(doc,page):
    t=page.get('text') or ''
    out=[]
    for expr,kind in ((SUBJECT,'explicit_subject_label'),(OBLIGATION,'party_obligation')):
        for m in expr.finditer(t):
            # Stop at the nearest section break or newline preserved by text extraction
            # (normalized page text has spaces; a section-heading stop still applies).
            snippet=t[m.end():min(len(t),m.end()+230)]
            stop=STOP.search(snippet)
            if stop: snippet=snippet[:stop.start()]
            ender=re.search(r'[;!?]|\.(?=\s+[А-ЯA-Z])',snippet)
            if ender: snippet=snippet[:ender.start()]
            value=snippet.strip(' :;,.\t\r\n-–')
            # An unbounded paragraph or heading is NOT a validated subject.
            if (len(value)<8 or not re.search(r'[А-Яа-яA-Za-z]',value)
                or BAD_SUBJECT.match(value) or len(value)>190):
                continue
            start=m.start(); end=m.end()+len(snippet)
            appendix=bool(re.search(r'(?i)\bприложение\s*(?:№\s*)?\d+',t[max(0,start-120):start]))
            out.append({'value':value, 'basis':kind,
                        'validity':'needs-review' if appendix else 'parsed',
                        'reason':'appendix_context' if appendix else 'explicit_bounded_subject',
                        'evidence':_evidence(doc,page,start,end,'subject')})
    # Structured heading on a separate line followed by the first bounded
    # sentence. This is not the heading itself and cannot borrow across a page.
    raw=page.get('raw_text') or ''
    head=re.search(r'(?im)^\s*\d*[.]?\s*Объект\s+закупки\s+и\s+исходные\s+условия\s*$',raw)
    if head:
        tail=raw[head.end():].strip()
        first=re.split(r'[.!?](?:\s|$)',tail,maxsplit=1)[0]
        first=re.sub(r'\s+',' ',first).strip()
        if 12 <= len(first) <= 190 and not BAD_SUBJECT.match(first):
            a=t.find(first)
            if a >= 0:
                out.append({'value':first, 'basis':'section_heading_first_sentence',
                            'validity':'parsed', 'reason':'bounded_object_section',
                            'evidence':_evidence(doc,page,a,a+len(first),'subject')})
    return out


def _table_candidates(doc,page):
    """Explicit native table cell pairs, not guesses from unrelated text."""
    amounts=[]; subjects=[]
    for table_index,table in enumerate(page.get('tables',[])):
        cells={(c['row'],c['column']):c for c in table.get('cells',[])}
        for (r,c),label_cell in cells.items():
            label=label_cell.get('value','').strip()
            if not label or len(label)>100: continue
            # Pair same-row label/value first, then table header/next-row value.
            partners=[(r,c+1),(r+1,c)]
            label_roles=[role for role,rx in ROLE_PATTERNS if rx.fullmatch(label)]
            is_subject=bool(SUBJECT.fullmatch(label+':'))
            for rr,cc in partners:
                v=cells.get((rr,cc))
                if not v:continue
                raw=v.get('value','').strip()
                if not raw:continue
                if label_roles:
                    value,reason=parse_rub_amount(raw)
                    if value is None:continue
                    eid=hashlib.sha256(f"{doc['sha256']}|{page['page']}|{table_index}|{r}:{c}|{rr}:{cc}".encode()).hexdigest()[:18]
                    ev={'id':'FD-T-'+eid,'file':doc['file'],'source_sha256':doc['sha256'],
                        'page':page['page'],'basis':'native_table_cells',
                        'table_index':table_index,'label_cell':[r,c], 'value_cell':[rr,cc],
                        'match':label+' -> '+raw,
                        'quote':label+' | '+raw,
                        'bbox':v.get('bbox'),'bbox_status':'native_cell' if v.get('bbox') else 'unavailable'}
                    amounts.append({'role':label_roles[0],'value':value,'currency':'RUB',
                        'validity':'parsed','reason':'table_label_value_pair',
                        'context':label+' | '+raw,'evidence':ev})
                    break
                if is_subject and 8<=len(raw)<=190 and not BAD_SUBJECT.match(raw):
                    eid=hashlib.sha256(f"{doc['sha256']}|{page['page']}|{table_index}|subject|{r}:{c}|{rr}:{cc}".encode()).hexdigest()[:18]
                    ev={'id':'FD-T-'+eid,'file':doc['file'],'source_sha256':doc['sha256'],
                        'page':page['page'],'basis':'native_table_cells','table_index':table_index,
                        'label_cell':[r,c], 'value_cell':[rr,cc], 'match':raw,
                        'quote':label+' | '+raw,
                        'bbox':v.get('bbox'),'bbox_status':'native_cell' if v.get('bbox') else 'unavailable'}
                    subjects.append({'value':raw, 'basis':'table_label_value',
                                     'validity':'parsed','reason':'table_subject_cell','evidence':ev})
                    break
    return amounts,subjects

def _summarize(candidates, prefer_roles=None):
    accepted=[r for r in candidates if r['validity']=='parsed' and
              (prefer_roles is None or r.get('role') in prefer_roles)]
    unique={r['value'] for r in accepted if r.get('value') is not None}
    if not candidates: return {'status':'not-found','value':None,'reason':'no_explicit_candidate'}
    if len(unique)==1 and len(accepted)==len(candidates):
        return {'status':'extracted','value':next(iter(unique)),'reason':'unique_explicit_candidate'}
    if len(unique)==1 and len(accepted)>0:
        return {'status':'needs-review','value':None,'reason':'other_candidates_or_roles'}
    return {'status':'needs-review','value':None,'reason':'no_unique_unambiguous_value'}


def build_normalized_card(documents):
    money=[];subjects=[]
    for doc in documents:
        for page in doc.get('pages',[]):
            money.extend(_money_for_page(doc,page))
            subjects.extend(_subjects_for_page(doc,page))
            from_table_money,from_table_subjects=_table_candidates(doc,page)
            money.extend(from_table_money)
            subjects.extend(from_table_subjects)
    # Actual price requires an explicit INITIAL maximum price role; contract
    # price, deposit/security and penalties are NEVER substituted for the budget.
    budget_candidates=[r for r in money if r['role']=='initial_maximum']
    budget=_summarize(budget_candidates)
    summary_subject=_summarize(subjects)
    return {'schema':'fast_dev_1.subject_price.v1',
            'budget_rub':{**budget,'evidence_ids':[r['evidence']['id'] for r in budget_candidates]},
            'subject':{**summary_subject,'evidence_ids':[r['evidence']['id'] for r in subjects]},
            'money_facts':money,'subject_candidates':subjects,
            'warnings':['structured_values_are_candidates_not_legal_conclusions',
                        'no_silent_budget_from_security_penalty_or_contract_price']}
