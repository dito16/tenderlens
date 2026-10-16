"""M09 scoring contract. Never represents synthetic/dev results as blind accuracy.

Input formats (JSON):
labels: {dataset_kind: 'dev_synthetic'|'independent_frozen',
         items:[{case_id,field,status:'present'|'absent'|'unknown',value?}],
predictions: {items:[{case_id,field,status:'predicted'|'abstain',value?}]}

For a *future* independent_frozen evaluation caller must additionally provide a
human verified, immutable manifest via --frozen-manifest; this tool does not make one.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import argparse
import json
from pathlib import Path

STATES={'present','absent','unknown'}
PRED_STATES={'predicted','abstain'}


def _key(obj):
    return (obj['case_id'], obj['field'])


def _unique(items,states,kind):
    seen={}
    for i in items:
        if not isinstance(i,dict) or not isinstance(i.get('case_id'),str) or not i['case_id'] or not isinstance(i.get('field'),str) or not i['field'] or i.get('status') not in states:
            raise ValueError('invalid_'+kind+'_item')
        k=_key(i)
        if k in seen:raise ValueError('duplicate_'+kind+'_item')
        if i['status']=='present' and 'value' not in i:raise ValueError('present_label_requires_value')
        if i['status']=='predicted' and 'value' not in i:raise ValueError('predicted_value_required')
        seen[k]=i
    return seen


def score(labels,predictions,*,frozen_manifest=None):
    kind=labels.get('dataset_kind')
    if kind not in ('dev_synthetic','independent_frozen'):raise ValueError('dataset_kind_required')
    if kind=='independent_frozen':
        if not isinstance(frozen_manifest,dict) or frozen_manifest.get('human_verified') is not True or frozen_manifest.get('frozen_before_predictions') is not True or not frozen_manifest.get('manifest_sha256'):
            raise ValueError('independent_scoring_requires_verified_frozen_manifest')
        raise ValueError('independent_holdout_not_available_in_this_release')
    truth=_unique(labels.get('items',[]),STATES,'label')
    pred=_unique(predictions.get('items',[]),PRED_STATES,'prediction')
    if not truth:raise ValueError('empty_labels')
    if set(pred)-set(truth):raise ValueError('prediction_without_label')
    groups=defaultdict(lambda:Counter())
    confusion=[]
    for key,label in sorted(truth.items()):
        stats=groups[label['field']];stats['labels_total']+=1
        p=pred.get(key,{'status':'abstain'})
        if label['status']=='unknown':
            stats['reference_unknown']+=1
            if p['status']=='predicted':stats['claims_on_reference_unknown']+=1
            confusion.append({'case_id':key[0],'field':key[1],'reference':'unknown','prediction':p['status'],'outcome':'unknown_reference_not_scored'})
            continue
        stats['scorable_labels']+=1
        if label['status']=='present':stats['reference_present']+=1
        else:stats['reference_absent']+=1
        if p['status']=='abstain':
            stats['abstained']+=1
            if label['status']=='present':stats['fn']+=1
            outcome='abstained'
        elif label['status']=='absent':
            stats['fp']+=1;outcome='false_positive_on_absent'
        elif str(p.get('value'))==str(label.get('value')):
            stats['tp']+=1;outcome='true_positive'
        else:
            stats['fp']+=1;stats['fn']+=1;outcome='wrong_value_fp_and_fn'
        confusion.append({'case_id':key[0],'field':key[1],'reference':label['status'],'expected_value':label.get('value'),
                          'prediction':p['status'],'predicted_value':p.get('value'),'outcome':outcome})
    per_field=[]
    for field,st in sorted(groups.items()):
        tp,fp,fn=st['tp'],st['fp'],st['fn']
        precision=tp/(tp+fp) if tp+fp else None
        recall=tp/(tp+fn) if tp+fn else None
        per_field.append({'field':field,'tp':tp,'fp':fp,'fn':fn,'precision':precision,'precision_numerator':tp,'precision_denominator':tp+fp,
                          'recall':recall,'recall_numerator':tp,'recall_denominator':tp+fn,'abstained':st['abstained'],
                          'reference_unknown':st['reference_unknown'],'claims_on_reference_unknown':st['claims_on_reference_unknown'],
                          'reference_present':st['reference_present'],'reference_absent':st['reference_absent'],
                          'scorable_labels':st['scorable_labels'],'labels_total':st['labels_total'],
                          'abstention_rate':st['abstained']/st['scorable_labels'] if st['scorable_labels'] else None})
    return {'schema':'tenderlens.qa.v1','dataset_kind':kind,'is_independent_evaluation':False,'blind_quality_estimate':None,
            'metrics':per_field,'confusion':confusion,'warnings':['DEVELOPMENT_ONLY: cannot infer unseen accuracy','unknown labels not treated as negatives',
            'abstentions on positive labels count as FN','small sample cannot establish safety'],
            'counts':{'labels':len(truth),'predictions':len(pred),'fields':len(per_field)}}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--labels',type=Path,required=True)
    p.add_argument('--predictions',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--frozen-manifest',type=Path)
    args=p.parse_args(argv)
    lab=json.loads(args.labels.read_text('utf-8'));pred=json.loads(args.predictions.read_text('utf-8'))
    frozen=json.loads(args.frozen_manifest.read_text('utf-8')) if args.frozen_manifest else None
    result=score(lab,pred,frozen_manifest=frozen)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('M09_DEV_METRICS_WRITTEN='+str(args.output))
    print('BLIND_METRICS=NOT_AVAILABLE')

if __name__=='__main__':main()
