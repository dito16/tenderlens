"""M05: explicit document revision metadata and cautious evidence-paired questions.

No precedence or legal conclusions: contradictory-looking candidates are review
questions, never a BID/NO-BID judgment or verified legal inconsistency.
"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path

ATTACHMENT_REF = re.compile(r'(?iu)(?:\bсм\.?\s*|\bсогласно\s+)?\bприложени[юяеи]\s*(?:№\s*)?(?P<number>\d{1,3})\b')
ATTACHMENT_NAME = re.compile(r'(?iu)\bприложени[ея]\s*(?:№\s*)?(\d{1,3})\b')
HISTORICAL = re.compile(r'(?iu)\b(?:предыдущая|старая|недействующая|отмен[её]нная)\s+редакция\b|\bцитата\s+старой\b')


def build_pack_manifest(documents, revision_hints=None):
    """Unknown remains unknown unless a user supplies explicit revision metadata.

    Hint: {filename:{revision:'v2', effective:'current|historical|unknown', scope:'...'}}
    effective describes manual source status, not inferred filename/time hierarchy.
    """
    revision_hints=revision_hints or {}
    names={d['file'] for d in documents}
    if len(names)!=len(documents):raise ValueError('duplicate_document_filenames_ambiguous')
    if set(revision_hints)-names:raise ValueError('revision_hint_for_unknown_document')
    result=[]
    for d in documents:
        name=d['file']; h=revision_hints.get(name,{})
        if not isinstance(h,dict) or set(h)-{'revision','effective','scope'}:
            raise ValueError('invalid_revision_hint')
        effective=h.get('effective','unknown')
        if effective not in ('current','historical','unknown'):
            raise ValueError('invalid_effective_status')
        sha=d['sha256']
        if not re.fullmatch(r'[0-9a-f]{64}',sha):raise ValueError('invalid_document_sha256')
        result.append({'document_id':sha,'file':name,'source_sha256':sha,
                       'role':d.get('document_role') or 'unknown',
                       'revision':str(h.get('revision','unknown')),
                       'effective':effective,
                       'scope':str(h.get('scope','unknown')),
                       'page_count':d['page_count']})
    return {'schema':'tenderlens.pack.v1','documents':result,
            'effective_rule':'explicit_hints_only_never_inferred',
            'warnings':['source_revision_not_attested','no_automatic_legal_precedence']}


def _value_key(f):
    return (str(f.get('value')),str(f.get('unit')),str(f.get('polarity','')))


def _qualifier(f):
    kind=f['kind']
    if kind=='warranty':return (kind,f.get('warranty_subject','unknown'))
    if kind=='term_duration':return (kind,f.get('term_kind','unknown'))
    if kind=='payment_delay':
        return (kind,_trigger(f.get('trigger')))
    if kind=='sro_requirement':return (kind, 'participant')
    if kind=='advance':return (kind,'advance')
    if kind=='submission_deadline':return (kind,'submission')
    return (kind,'unknown')


def _trigger(value):
    if not value:return None
    s=re.sub(r'\s+',' ',value.strip().lower().replace('ё','е'))
    if 'подписан' in s and 'акт' in s:return 'signed_acceptance_act'
    if 'приемк' in s:return 'acceptance'
    if 'поставк' in s:return 'delivery'
    if 'подписан' in s and 'договор' in s:return 'signed_contract'
    return s


def _pair(a,b,typ,reason,extra=None):
    ev1,ev2=a.get('evidence',{}),b.get('evidence',{})
    if not ev1.get('source_sha256') or not ev2.get('source_sha256'):return None
    raw='|'.join(sorted([str(ev1.get('id')),str(ev2.get('id'))]))+'|'+typ
    return {'id':'Q-'+hashlib.sha256(raw.encode()).hexdigest()[:18],
            'kind':typ,'status':'unresolved','severity':'needs_review',
            'legal_verdict':None,'reason':reason,
            'review_question':extra or 'Проверьте применимость редакций, предмета и формулировок обоих источников.',
            'evidence':[ev1,ev2],
            'fact_keys':[{'kind':a['kind'],'value':a.get('value'),'unit':a.get('unit')},
                         {'kind':b['kind'],'value':b.get('value'),'unit':b.get('unit')} ]}


def compare_pack(manifest, pipeline, documents):
    """Compare only cross-document, evidence-backed candidates with explicit limits."""
    byfile={d['file']:d for d in manifest['documents']}
    facts=[f for f in pipeline['facts'] if f['evidence']['file'] in byfile]
    candidates=[]; exclusions=[]
    for idx,a in enumerate(facts):
        role_a=byfile[a['evidence']['file']]
        for b in facts[idx+1:]:
            role_b=byfile[b['evidence']['file']]
            if role_a['document_id']==role_b['document_id']:continue
            if a['evidence']['file']==b['evidence']['file']:continue
            if a['kind']!=b['kind']:continue
            if a['kind'] not in {'sro_requirement','advance','submission_deadline','term_duration','payment_delay','warranty'}:continue
            if _qualifier(a)!=_qualifier(b):continue
            # Scope equality, even for SRO: differ -> don't flag as a conflict.
            sa,sb=role_a['scope'],role_b['scope']
            if sa!='unknown' and sb!='unknown' and sa!=sb:continue
            if role_a['effective']=='historical' or role_b['effective']=='historical':
                exclusions.append({'reason':'historical_revision_no_precedence','files':[role_a['file'],role_b['file']]});continue
            if a.get('review_required') or b.get('review_required'):continue
            q1,q2=(a.get('evidence',{}).get('quote',''),b.get('evidence',{}).get('quote',''))
            if HISTORICAL.search(q1) or HISTORICAL.search(q2):continue
            kind=a['kind']
            if kind in ('sro_requirement','advance'):
                if {(a.get('value') if kind=='sro_requirement' else a.get('polarity')), (b.get('value') if kind=='sro_requirement' else b.get('polarity'))}!={'explicit_positive','explicit_negative'}:continue
                if kind=='sro_requirement': typ='opposing_sro_wording'
                else:typ='opposing_advance_wording'
                question='Одинаков ли предмет работ и действуют ли обе формулировки? Не выводить юридический конфликт автоматически.'
            else:
                if a.get('value')==b.get('value') and a.get('unit')==b.get('unit'):continue
                if kind=='warranty' and (a.get('warranty_subject')=='unknown' or b.get('warranty_subject')=='unknown'):continue
                if kind=='payment_delay' and (_trigger(a.get('trigger')) is None or _trigger(b.get('trigger')) is None):continue
                if kind in ('payment_delay','term_duration') and a.get('unit')!=b.get('unit'):
                    typ='incompatible_day_units_question'
                    question='Рабочие и календарные дни не приведены к общему базису: уточнить условие, не считать конфликтом.'
                elif kind=='submission_deadline' and a.get('timezone','unknown')!=b.get('timezone','unknown'):
                    typ='timezone_question';question='Часовые пояса различаются или неизвестны. Уточнить до сравнения.'
                else:
                    typ='different_'+kind+'_wording'
                    question='Подтвердите одинаковую применимость условия, редакцию и точку отсчёта.'
            uncertain=(sa=='unknown' or sb=='unknown' or role_a['effective']=='unknown' or role_b['effective']=='unknown')
            item=_pair(a,b,typ,'source_scope_or_revision_unknown' if uncertain else 'cross_document_difference_requires_review',question)
            if item: candidates.append(item)
    # Separate non-assertive attachment questions from confirmed absence.
    referenced=[]; available=set(); seen_names={}; duplicate_names=[]
    for d in documents:
        filename=Path(d['file']).name
        seen_names.setdefault(filename.casefold(),[]).append(filename)
        hit=ATTACHMENT_NAME.search(filename.replace('_',' '))
        if hit:available.add(hit.group(1).lstrip('0') or '0')
        for p in d['pages']:
            txt=p.get('text','')
            for m in ATTACHMENT_REF.finditer(txt):
                num=m['number'].lstrip('0') or '0'
                if num not in available:
                    referenced.append({'file':filename,'source_sha256':d['sha256'],
                          'page':p['page'],'attachment_number':num,'quote':txt[max(0,m.start()-60):m.end()+60],
                          'status':'verify_pack_completeness_not_proven_missing'})
    for val in seen_names.values():
        if len(val)>1:duplicate_names.append(val)
    # Questions where no attachment with matching name was found; we cannot know if PDF bundles it.
    referenced=[r for r in referenced if r['attachment_number'] not in available]
    uniq={c['id']:c for c in candidates}
    return {'schema':'tenderlens.cross_document.v1','questions':list(uniq.values()),
            'attachment_questions':referenced[:150], 'duplicate_file_names':duplicate_names,
            'excluded_historical':exclusions[:150],
            'counts':{'questions':len(uniq),'attachment_questions':len(referenced)},
            'warnings':['questions_not_legal_conflicts','source_effective_status_must_be_manually_attested',
                        'unknown_document_scope_is_not_a_match','no_automatic_bid_verdict']}
