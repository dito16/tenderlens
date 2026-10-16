"""M03 limited, evidence-preserving RU clause polarity and cross-PDF review.

A classification describes explicit *wording*, not legal validity or priority.
Quoted/old-revision terms and unclear grammar fail closed. No registry calls.
"""
from __future__ import annotations
import hashlib
import re

# The inspection window never crosses a sentence boundary. PDF line-breaks
# are already normalized by the M01 page reader.
_BOUNDARY = re.compile(r'[.!?;\n]')  # periods inside dates/decimals are skipped by sentence()
_VERSION = re.compile(r'\b(?:прежн\w*\s+редакци\w*|стар\w*\s+редакци\w*|ранее\s+действовавш\w*|отмен[её]нн\w*\s+редакци\w*|цитат\w*|пример\s+формулировк\w*)\b', re.I)
_ADVANCE = re.compile(r'\bаванс\w*\b', re.I)
_PERCENT = re.compile(r'(?<!\d)(?:\d{1,3}(?:[.,]\d{1,2})?)\s*%', re.I)
_NEG_ADVANCE = re.compile(r'\b(?:аванс\w*\s*(?:\d{1,3}(?:[.,]\d{1,2})?\s*%)?\s*(?:не\s+предусмотрен\w*|отсутству\w*|отмен[её]н\w*)|без\s+аванса)\b', re.I)
_NEG_RETENTION = re.compile(r'\b(?:(?:гарантийн\w*\s+)?удержани[ея]\b[^.!?;]{0,145}?\b(?:не\s+предусмотрен\w*|отсутству\w*|не\s+применя\w*)|без\s+удержани[йя])\b', re.I)
_NEG_CHANGES = re.compile(r'\b(?:не\s+(?:производ\w*|выполня\w*|осуществля\w*|допуска\w*)|запрещен\w*)\b', re.I)
_NEG_SRO = re.compile(r'\b(?:СРО\s*[:–-]?\s*не\s+(?:требу\w*|обязател\w*|предусмотрен\w*)|членств\w*\s+в\s+СРО\s*[:–-]?\s*не\s+предусмотрен\w*|без\s+(?:обязательн\w*\s+)?СРО)\b', re.I)
_POS_SRO = re.compile(r'\b(?:требу\w*\s+(?:подтверждени\w*\s+членства\s+в\s+)?СРО|наличи\w*\s+СРО\s+обязательн\w*|СРО\s+обязательн\w*|членств\w*\s+в\s+СРО\s+требу\w*)\b', re.I)
_NEG_CLOSEOUT = re.compile(r'\b(?:КС\s*[-–]\s*[23]\s*(?:и\s*КС\s*[-–]\s*[23])?\s+не\s+(?:применя\w*|требу\w*|предусмотрен\w*))\b', re.I)
_SITE = re.compile(r'\b(?:обязательн\w*\s+осмотр\w*\s+объект\w*|осмотр\s+объекта)\b', re.I)
_NEG_SITE = re.compile(r'\b(?:осмотр\s+объекта\s+не\s+(?:обязателен|требуется)|осмотр\s+объекта\s+необязателен)\b', re.I)
_CONDITIONAL = re.compile(r'\b(?:если|при\s+условии|в\s+случае|может\s+потребова\w*)\b', re.I)


def _boundaries(text: str):
    """Find punctuation boundaries without splitting 01.09.2026 or 12.5%."""
    for hit in _BOUNDARY.finditer(text):
        index = hit.start()
        if (hit.group() == '.' and 0 < index < len(text)-1
                and text[index-1].isdigit() and text[index+1].isdigit()):
            continue
        yield hit


def sentence(text: str, start: int, end: int) -> tuple[str, int, int]:
    """Conservative clause window. Numbers and dates cannot sever revision context."""
    marks = list(_boundaries(text))
    begin = max((m.end() for m in marks if m.end() <= start), default=0)
    finish = next((m.start() for m in marks if m.start() >= end), len(text))
    return text[begin:finish].strip(), begin, finish


def classify(rule: str, text: str, start: int, end: int) -> tuple[str, str]:
    """Return explicit_positive, explicit_negative, mention, or unclear."""
    clause, _, _ = sentence(text, start, end)
    if _VERSION.search(clause):
        return 'unclear', 'quotation_or_previous_revision_requires_manual_review'
    if rule == 'advance':
        if _NEG_ADVANCE.search(clause):
            return 'explicit_negative', 'explicit_no_advance_wording'
        if _ADVANCE.search(clause) and _PERCENT.search(clause):
            if _CONDITIONAL.search(clause):
                return 'unclear', 'conditional_advance_wording'
            return 'explicit_positive', 'explicit_advance_percentage'
        return 'mention', 'no_explicit_advance_percentage'
    if rule == 'retention':
        if _NEG_RETENTION.search(clause):
            return 'explicit_negative', 'explicit_no_retention_wording'
        if _CONDITIONAL.search(clause):
            return 'unclear', 'conditional_retention_wording'
        if _PERCENT.search(clause) and re.search(r'удержани[ея]', clause, re.I):
            return 'explicit_positive', 'explicit_retention_percentage'
        return 'mention', 'retention_wording_only'
    if rule == 'unpriced_changes':
        suffix = clause[max(0, start - (sentence(text,start,end)[1])):]
        if _NEG_CHANGES.search(suffix):
            return 'explicit_negative', 'unpaid_works_disallowed_by_wording'
        if _CONDITIONAL.search(clause):
            return 'unclear', 'conditional_change_clause'
        return 'explicit_positive', 'unpriced_changes_mentioned'
    if rule == 'sro':
        if _NEG_SRO.search(clause):
            return 'explicit_negative', 'wording_sro_not_required'
        if _CONDITIONAL.search(clause):
            return 'unclear', 'sro_applicability_conditional'
        if _POS_SRO.search(clause):
            return 'explicit_positive', 'wording_sro_requirement'
        return 'mention', 'sro_reference_only'
    if rule == 'site_visit':
        if _NEG_SITE.search(clause):
            return 'explicit_negative', 'site_visit_not_mandatory_by_wording'
        if re.search(r'обязательн\w*\s+осмотр\w*\s+объект\w*|осмотр\s+объекта\s+обязателен', clause, re.I):
            return 'explicit_positive', 'site_visit_mandatory_wording'
        return 'mention', 'site_visit_reference_only'
    if rule == 'closeout':
        if _NEG_CLOSEOUT.search(clause):
            return 'explicit_negative', 'wording_ks_forms_not_applicable'
        return 'mention', 'ks_forms_mentioned'
    if rule == 'no_advance':
        return classify('advance',text,start,end)
    return 'mention', 'regex_wording_only'


def _proof(doc: dict, page: dict, start: int, end: int, family: str) -> dict:
    text=page['text']
    key=f"{doc['sha256']}|{page['page']}|{family}|{start}|{end}".encode('utf-8')
    s=max(0,start-55);e=min(len(text),end+70)
    return {'id':'CL-'+hashlib.sha256(key).hexdigest()[:20],
            'file':doc['file'], 'source_sha256':doc['sha256'],
            'page':page['page'],'match':text[start:end],
            'normalized_span':[start,end],'span_basis':'normalized_page_text',
            'quote':text[s:e]}


def advance_conditions(documents: list[dict]) -> list[dict]:
    items=[]
    for doc in documents:
        for page in doc['pages']:
            text=page.get('text') or ''
            for hit in _ADVANCE.finditer(text):
                polarity,basis=classify('advance',text,*hit.span())
                # Only claims with an explicit advance percentage or explicit
                # absence can be used in a cross-file contradiction.
                if polarity in ('explicit_positive','explicit_negative','unclear'):
                    clause,_,_=sentence(text,*hit.span())
                    items.append({'family':'advance_terms','polarity':polarity,
                                  'reason':basis, 'clause':clause,
                                  'evidence':_proof(doc,page,*hit.span(),'advance_terms')})
    return items


def conflicts_for_review(conditions: list[dict]) -> list[dict]:
    positive=[c for c in conditions if c['polarity']=='explicit_positive']
    negative=[c for c in conditions if c['polarity']=='explicit_negative']
    pairs=next(((a,b) for a in positive for b in negative
                if a['evidence']['file']!=b['evidence']['file']),None)
    if not pairs:
        return []
    a,b=pairs
    return [{'family':'advance_terms','status':'needs-review',
             'human_review_required':True,
             'reason':'opposing_explicit_wording_in_distinct_documents_no_revision_priority',
             'evidence_ids':[a['evidence']['id'],b['evidence']['id']],
             'evidence':[a['evidence'],b['evidence']],
             'question':'Какое условие об авансе действует? Проверьте редакции и оригинальные страницы.'}]



def additional_review_conflicts(conditions: list[dict], typed_fields: dict) -> list[dict]:
    """Flag wording disagreements, not legal contradictions or unit conversions."""
    output = []
    sro = [row for row in conditions if row['family'] == 'sro_wording']
    pos = [row for row in sro if row['polarity'] == 'explicit_positive']
    neg = [row for row in sro if row['polarity'] == 'explicit_negative']
    pair = next(((a, b) for a in pos for b in neg
                 if a['evidence']['file'] != b['evidence']['file']), None)
    if pair:
        a, b = pair
        output.append({
            'family': 'sro_scope', 'status': 'needs-review',
            'human_review_required': True,
            'reason': 'opposing_sro_wording_scope_or_work_type_may_differ',
            'evidence': [a['evidence'], b['evidence']],
            'evidence_ids': [a['evidence']['id'], b['evidence']['id']],
            'question': 'В одном документе СРО требуется, в другом исключено для части работ. Сопоставьте виды работ и область действия.'})

    candidates = typed_fields.get('duration', {}).get('candidates', [])
    parsed = [c for c in candidates if c['validity'] == 'parsed']
    duration_pair = next(((a, b) for a in parsed for b in parsed
                          if a['evidence']['file'] != b['evidence']['file']
                          and (a['value'], a['unit']) != (b['value'], b['unit'])), None)
    if duration_pair:
        a, b = duration_pair
        output.append({
            'family': 'duration_terms', 'status': 'needs-review',
            'human_review_required': True,
            'reason': 'different_declared_duration_values_or_units_no_calendar_conversion',
            'declared_values': [{'value': c['value'], 'unit': c['unit']}
                                for c in duration_pair],
            'evidence': [a['evidence'], b['evidence']],
            'evidence_ids': [a['evidence']['id'], b['evidence']['id']],
            'question': 'Указаны разные сроки или единицы. Сверьте точки отсчёта и редакции, не приравнивая рабочие дни к календарным.'})
    return output


def clause_conditions(documents: list[dict]) -> list[dict]:
    """Additional narrow review categories; never a compliance judgement."""
    families=(('retention_terms',re.compile(r'\bудержани[ея]\b',re.I),'retention'),
              ('unpriced_changes',re.compile(r'\bбез\s+(?:увеличения\s+цен[ыа]|дополнительн\w*\s+оплат[ыа]|доплат[ыа])\b',re.I),'unpriced_changes'),
              ('sro_wording',re.compile(r'\bСРО\b',re.I),'sro'),
              ('site_visit',_SITE,'site_visit'),
              ('acceptance_ks',re.compile(r'\bКС\s*[-–]\s*[23]\b',re.I),'closeout'))
    output=[]
    for doc in documents:
        for page in doc['pages']:
            text=page.get('text') or ''
            for family,pattern,rule in families:
                for match in pattern.finditer(text):
                    polarity,basis=classify(rule,text,*match.span())
                    item={'family':family,'polarity':polarity,'reason':basis,
                          'evidence':_proof(doc,page,*match.span(),family)}
                    output.append(item)
    return output
