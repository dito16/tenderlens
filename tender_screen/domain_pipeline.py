"""FAST DEV 2: bounded evidence-first work scopes and commercial/legal clauses.

This is a **candidate** extraction layer, not a legal verdict or a gold label.
No cross-page borrowing, no inferred price from quantity, no clock timezone guess.
Existing R4/R5/FD1 extractors and legacy outputs remain untouched.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import re
from typing import Iterable

from .pdf_layout import span_bbox
from .real_terms import _parse_date

NUM = r"(?P<n>\d{1,7}(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d{1,3})?)"
DAY_KIND = r"(?P<daykind>рабочих|календарных)?\s*дн(?:ей|я|ь)"
DATE = r"(?:\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4}(?:\s+года)?)"
# Initial numeric format with optional thousand separators and Russian decimal comma.
QUANTITY = re.compile(r"(?<![\d.,])(?P<value>\d{1,7}(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d{1,3})?)\s*"
    r"(?P<unit>шт(?:ук[аи])?\.?|м²|м2|кв\.?\s*м\.?|м³|м3|куб\.?\s*м\.?|пог\.?\s*м\.?|"
    r"км|кг|тонн(?:а|ы)?|т\b|комплект(?:а|ов)?|единиц(?:а|ы)?)\b", re.I)
SCOPE_CONTEXT = re.compile(r'(?i)\b(?:ведомост[ьи]\s+об[ъь]?[её]мов|дефектн\w*\s+ведомост[ьи]|количеств\w*|об[ъь]?[её]м\w*\s+работ|позици[яи]|спецификаци[яи])\b')
GOODS = re.compile(r'(?i)\b(?:поставка|поставить|поставщик|товар(?:ов|а|ы)?|материал(?:ы|ов)|оборудовани[ея])\b')
SERVICE = re.compile(r'(?i)\b(?:оказани[ея]\s+услуг|оказать\s+услуг|услуги|обслуживани[ея]|консультаци[яи]|уборк[иа])\b')
WORK = re.compile(r'(?i)\b(?:строительств[оа]|ремонт\w*|монтаж\w*|реконструкци[яи]|подрядн\w*\s+работ|выполнени[ея]\s+работ)\b')
HEDGING = re.compile(r'(?i)\b(?:ориентировочн\w*|примерн\w*|уточня\w*|не\s+более|до\s+\d|от\s+\d)\b')

# Patterns start with field context and only search within a bounded clause.
DEADLINE = re.compile(r'(?i)(?P<label>срок\s+(?:подачи|при[её]ма)\s+(?:заявок|предложений)|'
    r'(?:окончание|завершение)\s+(?:подачи|при[её]ма)\s+заявок|при[её]м\s+заявок|'
    r'подача\s+заявок|заявки\s+принимаются)'
    rf'(?P<between>.{{0,85}}?)\b(?P<boundary>не\s+позднее|до|по)\s*(?P<date>{DATE})'
    r'(?:\s*(?:г\.?|года))?(?:\s+(?:в|до)\s*(?P<clock>\d{1,2}:\d{2}))?', re.I)
TERM = re.compile(r'(?i)(?P<label>срок\s+(?:поставки|выполнения\s+работ|оказания\s+услуг|'
    r'исполнения\s+договора)|поставка\s+товара|срок\s+выполнения\s+заявки|'
    r'срок\s+подготовки\s+схемы)'
    rf'.{{0,75}}?(?P<value>\d{{1,3}})\s*{DAY_KIND}',re.I)
PAYMENT = re.compile(r'(?i)(?P<label>оплат[аыуе]|расч[её]т\w*)\b.{0,110}?'
    rf'(?:в\s+течение|не\s+позднее|через|в\s+срок)\s*(?P<value>\d{{1,3}})\s*{DAY_KIND}', re.I)
ADVANCE = re.compile(r'(?i)\b(?:аванс\w*|предоплат\w*)\b.{0,80}')
WARRANTY = re.compile(r'(?i)\b(?P<label>гарантийн\w*\s+срок|гаранти[яи]\s+на)\b'
    r'(?P<subject>.{0,100}?)(?:составляет|устанавливается|не\s+менее|равен|[:–-])\s*'
    r'(?P<value>\d{1,3})\s*(?P<unit>месяц(?:ев|а|ы)?|лет|года|год)\b',re.I)
SRO = re.compile(r'(?i)\b(?:СРО|саморегулируем\w*\s+организаци\w*)\b')
SITE = re.compile(r'(?i)\bосмотр\w*\s+объект\w*\b')
NEGATION = re.compile(r'(?i)\b(?:не\s+требу\w*|не\s+предусмотрен\w*|не\s+устанавлива\w*|не\s+нужн\w*|не\s+обязател\w*|без\s+(?:аванс\w*|предоплат\w*|СРО))\b')
AFFIRM = re.compile(r'(?i)\b(?:обязател\w*|должен|должна|требу\w*|необходимо|наличие|предусмотрен\w*)\b')
CONDITIONAL = re.compile(r'(?i)\b(?:если|при\s+условии|в\s+случае|за\s+исключением|кроме|только\s+при)\b')
OLD = re.compile(r'(?i)\b(?:старая\s+редакция|предыдущая\s+редакция|отмененн\w*\s+услови\w*|недействующая\s+редакция|пример\s+формулировки|цитат[аы])\b')
TRIGGER = re.compile(r'(?i)\b(?:после\s+подписани\w*\s+акт\w*|после\s+при[её]мки|с\s+момента\s+при[её]мки|'
    r'со\s+дня\s+получени\w*\s+заявк\w*|после\s+поставки|после\s+подписания\s+договора)\b')


def _chunks(text: str) -> Iterable[tuple[int,str]]:
    """Local clause windows; '.' in dates, fractions, and decimals is not a stop."""
    start=0
    for match in re.finditer(r'[;!?]|(?<!\d)\.(?!\d)(?=\s|$)',text):
        end=match.start()
        if end>start and len(text[start:end].strip()) > 0:
            yield start,text[start:end]
        start=match.end()
    if text[start:].strip():
        yield start,text[start:]


def _evidence(doc,page,start,end,kind):
    text=page['text']
    assert 0<=start<end<=len(text)
    match=text[start:end]
    ident=hashlib.sha256(f"{doc['sha256']}|{page['page']}|{start}|{end}|{kind}".encode()).hexdigest()[:20]
    bbox=span_bbox(page,start,end)
    return {'id':'FD2-'+ident,'file':doc['file'],'source_sha256':doc['sha256'],
            'page':page['page'],'normalized_span':[start,end], 'span_basis':'normalized_page_text',
            'match':match,'quote':text[max(0,start-65):min(len(text),end+70)],
            'bbox':bbox,'bbox_status':'verified_words' if bbox is not None else 'unavailable'}


def _fact(doc,page,kind,value,unit,start,end,**extras):
    return {'kind':kind,'value':value,'unit':unit,'status':'candidate',
            'review_required':extras.pop('review_required',False),
            'evidence':_evidence(doc,page,start,end,kind),**extras}


def _scope_kind(piece):
    kinds=[]
    if WORK.search(piece):kinds.append('construction_work')
    if SERVICE.search(piece):kinds.append('service')
    if GOODS.search(piece):kinds.append('goods')
    return kinds[0] if len(kinds)==1 else 'mixed_or_unknown'


def _quantity(raw):
    try:
        x=Decimal(re.sub(r'[ \u00a0\u202f]','',raw).replace(',','.'))
    except InvalidOperation:
        return None
    if not x.is_finite() or x<=0 or x>Decimal('1000000000'):
        return None
    return format(x,'f')


def _first_date(raw):
    return _parse_date(raw)


def _extract_one(doc,page):
    t=page['text']; facts=[]; rejected=[]
    for offset,piece in _chunks(t):
        if not piece.strip():continue
        # Long PDF pages with unrelated clauses: only tight local evidence.
        is_heading=bool(SCOPE_CONTEXT.search(piece[:125]))
        if is_heading or (re.search(r'(?i)\b(?:выполнить|поставить)\b',piece[:95]) and len(piece)<180):
            for m in list(QUANTITY.finditer(piece))[:30]:
                before=piece[max(0,m.start()-90):m.start()]
                # Unit & numeric proof together, reject numbers after price indicators.
                if re.search(r'(?i)(?:цена|стоимость|НМЦК|руб\.?|₽)\s*[:–-]?\s*$',before):
                    rejected.append({'reason':'quantity_in_price_context','file':doc['file'],'page':page['page'],
                        'span':[offset+m.start(),offset+m.end()]});continue
                qty=_quantity(m['value'])
                if qty is None:
                    rejected.append({'reason':'invalid_quantity','file':doc['file'],'page':page['page'],
                        'span':[offset+m.start(),offset+m.end()]});continue
                unit=re.sub(r'\s+','',m['unit'].lower().replace('²','2').replace('³','3')).rstrip('.')
                kind=_scope_kind(piece[max(0,m.start()-110):min(len(piece),m.end()+65)])
                facts.append(_fact(doc,page,'work_scope',qty,unit,offset+m.start(),offset+m.end(),
                    scope_kind=kind,scope_excerpt=piece[max(0,m.start()-80):min(len(piece),m.end()+65)].strip(),
                    review_required=kind=='mixed_or_unknown' or bool(HEDGING.search(before))))
        for m in DEADLINE.finditer(piece):
            d=_first_date(m['date'])
            if d is None:
                rejected.append({'reason':'invalid_submission_date','file':doc['file'],'page':page['page']});continue
            clock=m.group('clock')
            if clock and (int(clock[:2])>23 or int(clock[3:])>59):
                rejected.append({'reason':'invalid_time','file':doc['file'],'page':page['page']});continue
            facts.append(_fact(doc,page,'submission_deadline',d,'date',offset+m.start(),offset+m.end(),
                clock=clock,timezone='unknown',boundary=m['boundary'].lower().replace(' ','_'),
                review_required=bool(OLD.search(piece[:m.start()]))))
        for m in TERM.finditer(piece):
            n=int(m['value'])
            if not (0<n<=3650):continue
            label=m['label'].lower()
            kind=('request_sla' if 'заявк' in label else 'scheme_preparation' if 'схем' in label else
                  'delivery' if 'поставк' in label else 'services' if 'услуг' in label else 'work_execution')
            unit=('work_days' if (m['daykind'] or '').lower()=='рабочих' else
                  'calendar_days' if (m['daykind'] or '').lower()=='календарных' else 'days_unspecified')
            trigger=TRIGGER.search(piece[m.end():m.end()+120])
            facts.append(_fact(doc,page,'term_duration',str(n),unit,offset+m.start(),offset+m.end(),
                term_kind=kind,reference_event=trigger.group(0) if trigger else None,
                review_required=unit=='days_unspecified'))
        for m in PAYMENT.finditer(piece):
            n=int(m['value'])
            if n==0 or n>3650:continue
            unit='work_days' if (m['daykind'] or '').lower()=='рабочих' else 'calendar_days' if (m['daykind'] or '').lower()=='календарных' else 'days_unspecified'
            trig=TRIGGER.search(piece[max(0,m.start()-55):min(len(piece),m.end()+90)])
            facts.append(_fact(doc,page,'payment_delay',str(n),unit,offset+m.start(),offset+m.end(),
                trigger=trig.group(0) if trig else None,polarity='affirmative',
                review_required=trig is None or unit=='days_unspecified'))
        am=ADVANCE.search(piece)
        if am:
            local=piece[max(0,am.start()-25):am.end()]
            if OLD.search(piece[:am.start()]):pol='historical_or_quoted'
            elif re.search(r'(?i)(?:аванс\w*|предоплат\w*)\s*(?:не\s+предусмотрен\w*|отсутству\w*|не\s+выплачива\w*)|без\s+(?:аванса|предоплаты)|не\s+предусмотрен\w*\s+аванс',local):pol='explicit_negative'
            elif re.search(r'(?i)(?:аванс\w*|предоплат\w*)\s*(?:предусмотрен\w*|составляет|в\s+размере)\s*\d{1,3}\s*%',local):pol='explicit_positive'
            else:pol='mention_only'
            rate_match = re.search(r'(?i)(?:аванс\w*|предоплат\w*)\s*(?:предусмотрен\w*|составляет|в\s+размере)\s*(\d{1,3}(?:[.,]\d{1,2})?)\s*%', local)
            percent = rate_match.group(1).replace(',', '.') if rate_match and pol == 'explicit_positive' else None
            # Replace null with an explicit, evidence-backed polarity, preserve source match/span.
            facts.append(_fact(doc,page,'advance',pol,'polarity',offset+am.start(),offset+am.end(),
                polarity=pol,advance_percent=percent,
                review_required=pol in ('mention_only','historical_or_quoted')))
        for m in WARRANTY.finditer(piece):
            n=int(m['value'])
            if n<=0:continue
            subject=m['subject'].lower()
            kind=('materials' if re.search(r'материал|оборудован|издели|товар',subject) else
                  'works' if re.search(r'работ|ремонт|монтаж',subject) else
                  'services' if 'услуг' in subject else 'unknown')
            unit='months' if m['unit'].lower().startswith('месяц') else 'years'
            facts.append(_fact(doc,page,'warranty',str(n),unit,offset+m.start(),offset+m.end(),
                warranty_subject=kind,review_required=kind=='unknown'))
        for pattern,kind in ((SRO,'sro_requirement'),(SITE,'site_visit_requirement')):
            for m in list(pattern.finditer(piece))[:8]:
                # Polarity is local to the mention; a negative in another sentence can't leak.
                near=piece[max(0,m.start()-75):min(len(piece),m.end()+75)]
                if OLD.search(piece[max(0,m.start()-80):m.start()]):pol='historical_or_quoted'
                elif CONDITIONAL.search(near):pol='conditional_or_exception'
                elif NEGATION.search(near):pol='explicit_negative'
                elif AFFIRM.search(near):pol='explicit_positive'
                else:pol='mention_only'
                facts.append(_fact(doc,page,kind,pol,'polarity',offset+m.start(),offset+m.end(),
                    actor='participant' if kind=='sro_requirement' else 'unspecified',
                    modality='requirement' if pol=='explicit_positive' else 'not_required' if pol=='explicit_negative' else 'unverified',
                    review_required=pol in ('mention_only','historical_or_quoted','conditional_or_exception')))
    return facts,rejected



def _table_scope_facts(doc, page):
    """Quantities from actual native cells with row/column provenance, not regex text joins."""
    out=[]
    for ti,tab in enumerate(page.get('tables',[])):
        cells={(x['row'],x['column']):x for x in tab.get('cells',[])}
        headers={}
        for (r,c),cell in cells.items():
            if r>1: continue
            v=(cell.get('value') or '').strip().lower()
            if re.search(r'(?i)^(?:количество|кол-во|об[ъь]?[её]м(?: работ)?|qty)\s*$',v):headers['quantity']=(r,c)
            if re.search(r'(?i)^(?:ед\.?\s*(?:изм\.?|измерения)|единица измерения)\s*$',v):headers['unit']=(r,c)
            if re.search(r'(?i)^(?:наименование|наименование работ|вид работ|описание)\s*$',v):headers['description']=(r,c)
        if 'quantity' not in headers:continue
        headrow,qtycol=headers['quantity']
        for row in range(headrow+1,min(int(tab.get('row_count',1000)),1000)):
            qtycell=cells.get((row,qtycol))
            if not qtycell or not (qtycell.get('value') or '').strip():continue
            raw=qtycell['value'].strip()
            ucell=None
            if 'unit' in headers:
                ucell=cells.get((row,headers['unit'][1]))
            unittext=(ucell.get('value','') if ucell else '').strip()
            candidate=raw if QUANTITY.fullmatch(raw) else (raw+' '+unittext)
            m=QUANTITY.fullmatch(candidate)
            if m is None:continue
            value=_quantity(m['value'])
            if value is None:continue
            desc_cell=cells.get((row,headers['description'][1])) if 'description' in headers else None
            desc=(desc_cell.get('value','') if desc_cell else '').strip()
            unit=re.sub(r'\s+','',m['unit'].lower().replace('²','2').replace('³','3')).rstrip('.')
            kind=_scope_kind(desc)
            ev_id=hashlib.sha256(f"{doc['sha256']}|{page['page']}|{ti}|{row}|{qtycol}|{raw}|{unittext}".encode()).hexdigest()[:20]
            ev={'id':'FD2-T-'+ev_id,'file':doc['file'],'source_sha256':doc['sha256'],
                'page':page['page'],'basis':'native_table_cells', 'table_index':ti,
                'value_cell':[row,qtycol], 'unit_cell':[row,headers['unit'][1]] if ucell else None,
                'match':raw,'unit_match':unittext,'quote':' | '.join(x for x in (desc,raw,unittext) if x),
                'bbox':qtycell.get('bbox'),'bbox_status':'native_cell' if qtycell.get('bbox') else 'unavailable'}
            out.append({'kind':'work_scope','value':value,'unit':unit,'status':'candidate',
                'review_required':kind=='mixed_or_unknown', 'scope_kind':kind,
                'scope_excerpt':desc,'evidence':ev})
    return out


def validate_pipeline(documents, facts, rejected):
    lookup={(doc['file'],doc['sha256']):doc for doc in documents}
    valid=[]
    for item in facts:
        ev=item['evidence']; doc=lookup.get((ev['file'],ev['source_sha256']))
        page=next((p for p in doc['pages'] if p['page']==ev['page']),None) if doc else None
        if page is None:
            rejected.append({'reason':'evidence_source_missing','evidence_id':ev['id']})
            continue
        if ev.get('basis')=='native_table_cells':
            idx=ev['table_index']
            if not(0<=idx<len(page.get('tables',[]))):
                rejected.append({'reason':'missing_native_table','evidence_id':ev['id']});continue
            cells={(c['row'],c['column']):c for c in page['tables'][idx]['cells']}
            q=cells.get(tuple(ev['value_cell']))
            u=cells.get(tuple(ev['unit_cell'])) if ev['unit_cell'] is not None else None
            if (q is None or q.get('value','').strip()!=ev['match'] or
                    (ev['unit_cell'] is not None and (u is None or u.get('value','').strip()!=ev['unit_match']))):
                rejected.append({'reason':'native_cell_value_changed','evidence_id':ev['id']});continue
        else:
            a,b=ev['normalized_span']
            if not(0<=a<b<=len(page['text'])) or page['text'][a:b]!=ev['match']:
                rejected.append({'reason':'unverifiable_evidence_span', 'evidence_id':ev['id']});continue
        valid.append(item)
    return valid


def build_domain_pipeline(documents):
    facts=[]; rejected=[]
    for doc in documents:
        for page in doc['pages']:
            items, drops=_extract_one(doc,page)
            facts.extend(items)
            facts.extend(_table_scope_facts(doc,page))
            rejected.extend(drops)
    facts=validate_pipeline(documents,facts,rejected)
    facts.sort(key=lambda item:(item['evidence']['file'],item['evidence']['page'],item['evidence'].get('normalized_span',[10**9])[0],item['evidence'].get('table_index',-1),item['kind']))
    # Deduplicate identical candidate and evidence boundaries.
    seen=set();unique=[]
    for row in facts:
        key=(row['kind'],row['value'],row.get('unit'),row['evidence']['id'])
        if key not in seen: seen.add(key);unique.append(row)
    facts=unique
    contradictions=[]
    for kind in ('submission_deadline','advance','warranty','payment_delay','term_duration'):
        subset=[f for f in facts if f['kind']==kind]
        by_scope={}
        for x in subset:
            scope=x.get('warranty_subject') if kind=='warranty' else x.get('term_kind') if kind=='term_duration' else 'shared'
            if x.get('review_required'):continue
            by_scope.setdefault(scope,[]).append(x)
        for scope,items in by_scope.items():
            values={(x.get('value'),x.get('unit')) for x in items}
            if len(values)>1:
                contradictions.append({'kind':kind,'scope':scope,'evidence_ids':[x['evidence']['id'] for x in items],
                    'status':'needs_review_not_automatically_resolved'})
    return {'schema':'fast_dev_2.evidence_pipeline.v1','facts':facts,
            'rejections':rejected,'possible_conflicts':contradictions,
            'counts':{'facts':len(facts),'rejections':len(rejected),'possible_conflicts':len(contradictions)},
            'warnings':['candidate_only_not_legal_verdict','no_auto_legal_precedence',
                        'no_time_zone_assumptions','no_quantity_price_multiplication','not_blind_validation']}
