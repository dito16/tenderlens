"""Reproducible development regression only; no hidden corpus or blind metric."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from tender_screen.core import analyze_folder
from tender_screen.pack import build_pack_manifest,compare_pack
from .evaluate import score
from .evidence import audit


def run(pdf_dir,out):
    paths=sorted(pdf_dir.glob('*.pdf'))
    if len(paths)!=3 or [p.name for p in paths]!=['01_notice.pdf','02_technical.pdf','03_contract.pdf']:
        raise ValueError('dev_only_three_expected_synthetic_pdfs')
    output=analyze_folder(pdf_dir)
    if output.get('processing_status')!='complete':raise ValueError('dev_analysis_incomplete')
    facts=output['fast_dev2']['facts']
    questions=compare_pack(build_pack_manifest(output['layout']),output['fast_dev2'],output['layout'])['questions']
    # The dev oracles were authored for this publicly disclosed *synthetic* set.
    oracles={('01_notice.pdf','submission_deadline'):'2026-11-23',
      ('01_notice.pdf','sro_requirement'):'explicit_positive',
      ('01_notice.pdf','advance'):'explicit_positive',
      ('01_notice.pdf','payment_delay'):'10',
      ('02_technical.pdf','work_scope'):'125',
      ('03_contract.pdf','sro_requirement'):'explicit_negative',
      ('03_contract.pdf','advance'):'explicit_negative',
      ('03_contract.pdf','payment_delay'):'20',
      ('03_contract.pdf','warranty'):'36'}
    label_items=[{'case_id':file,'field':kind,'status':'present','value':val} for (file,kind),val in sorted(oracles.items())]
    pred_items=[]
    for fact in facts:
        k=(fact['evidence']['file'],fact['kind'])
        if k in oracles: pred_items.append({'case_id':k[0],'field':k[1], 'status':'predicted','value':fact.get('value')})
    if len(pred_items)!=len(oracles):
        raise ValueError('dev_regression_missing_or_duplicate_candidates')
    labels={'dataset_kind':'dev_synthetic','items':label_items}
    predictions={'items':pred_items}
    metrics=score(labels,predictions)
    proofs=audit(output)
    if not proofs['pass']:raise AssertionError('evidence_failure')
    detected={q['kind'] for q in questions}
    expected={'opposing_sro_wording','opposing_advance_wording','different_payment_delay_wording'}
    if detected!=expected or len(questions)!=3:raise AssertionError('regression_questions_mismatch')
    out.mkdir(parents=True,exist_ok=True)
    for name,item in [('DEV_LABELS.json',labels),('DEV_PREDICTIONS.json',predictions),('DEV_METRICS.json',metrics),('DEV_EVIDENCE_AUDIT.json',proofs),
                      ('DEV_SUMMARY.json',{'dataset_kind':'dev_synthetic','pdfs':3,'facts':len(facts),'questions':len(questions),
                          'matches':len(oracles),'not_blind':True, 'blind_quality':None,
                          'sha256':[{'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]})]:
        (out/name).write_text(json.dumps(item,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('DEV_REGRESSION=PASS facts='+str(len(facts))+' review_questions='+str(len(questions)))
    print('DEV_EVIDENCE_INTEGRITY=PASS '+str(proofs['checks']))
    print('INDEPENDENT_M09=BLOCKED_NO_FROZEN_HUMAN_HOLDOUT')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,default=Path('examples/fast_dev3_conflict_pack'))
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.input,a.out)
if __name__=='__main__':main()
