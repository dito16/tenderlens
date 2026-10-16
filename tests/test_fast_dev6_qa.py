import copy
import json
import tempfile
import unittest
from pathlib import Path
from qa.evaluate import score
from qa.evidence import audit


def labels(*xs):return {'dataset_kind':'dev_synthetic','items':list(xs)}
def item(c='a',f='price',status='present',value='10'):
    x={'case_id':c,'field':f,'status':status}
    if status=='present':x['value']=value
    return x
def pred(c='a',f='price',value='10',status='predicted'):
    x={'case_id':c,'field':f,'status':status}
    if status=='predicted':x['value']=value
    return x

class EvaluationMetrics(unittest.TestCase):
    def test_tp(self):
        m=score(labels(item()),{'items':[pred()]})['metrics'][0]
        self.assertEqual((m['tp'],m['precision'],m['recall']),(1,1,1))
    def test_fp_on_absent(self):
        m=score(labels(item(status='absent')),{'items':[pred()]})['metrics'][0]
        self.assertEqual((m['tp'],m['fp'],m['fn'],m['precision']),(0,1,0,0))
        self.assertIsNone(m['recall'])
    def test_wrong_value_fp_fn(self):
        m=score(labels(item()),{'items':[pred(value='20')]})['metrics'][0]
        self.assertEqual((m['tp'],m['fp'],m['fn']),(0,1,1))
    def test_abstention_positive_is_fn(self):
        m=score(labels(item()),{'items':[pred(status='abstain')]})['metrics'][0]
        self.assertEqual((m['fn'],m['abstained'],m['recall']),(1,1,0))
    def test_missing_prediction_is_abstain(self):
        m=score(labels(item()),{'items':[]})['metrics'][0]
        self.assertEqual((m['fn'],m['abstained']),(1,1))
    def test_abstention_negative_is_not_fp(self):
        m=score(labels(item(status='absent')),{'items':[pred(status='abstain')]})['metrics'][0]
        self.assertEqual((m['fp'],m['fn']),(0,0))
    def test_unknown_gold_not_true_negative(self):
        m=score(labels(item(status='unknown')),{'items':[pred()]})['metrics'][0]
        self.assertEqual((m['reference_unknown'],m['claims_on_reference_unknown']),(1,1))
        self.assertIsNone(m['precision']);self.assertEqual(m['scorable_labels'],0)
    def test_field_separation(self):
        m=score(labels(item(),item('b','scope',status='present',value='x')),
             {'items':[pred(),pred('b','scope',value='x')]})
        self.assertEqual(len(m['metrics']),2)
    def test_duplicate_labels_refused(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):score(labels(item(),item()),{'items':[]})
    def test_duplicate_predictions_refused(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):score(labels(item()),{'items':[pred(),pred()]})
    def test_hallucinated_case_refused(self):
        with self.assertRaisesRegex(ValueError,'prediction_without_label'):score(labels(item()),{'items':[pred('b')]})
    def test_empty_labels_refused(self):
        with self.assertRaisesRegex(ValueError,'empty_labels'):score(labels(),{'items':[]})
    def test_bad_status_refused(self):
        with self.assertRaisesRegex(ValueError,'invalid_label_item'):score(labels(item(status='made_up')),{'items':[]})
    def test_missing_present_value_refused(self):
        with self.assertRaisesRegex(ValueError,'present_label_requires_value'):score(labels({'case_id':'x','field':'q','status':'present'}),{'items':[]})
    def test_missing_prediction_value_refused(self):
        with self.assertRaisesRegex(ValueError,'predicted_value_required'):score(labels(item()),{'items':[{'case_id':'a','field':'price','status':'predicted'}]})
    def test_bad_dataset_refused(self):
        with self.assertRaisesRegex(ValueError,'dataset_kind_required'):score({'items':[item()]},{'items':[]})
    def test_holdout_not_claimable(self):
        with self.assertRaisesRegex(ValueError,'verified_frozen_manifest'):score({'dataset_kind':'independent_frozen','items':[item()]},{'items':[pred()]})
    def test_holdout_with_fake_manifest_refused(self):
        with self.assertRaisesRegex(ValueError,'independent_holdout_not_available'):score({'dataset_kind':'independent_frozen','items':[item()]},{'items':[pred()]},frozen_manifest={'human_verified':True,'frozen_before_predictions':True,'manifest_sha256':'x'*64})
    def test_numerator_denominator(self):
        m=score(labels(item('a'),item('b'),item('c',status='absent')),
                {'items':[pred('a'),pred('b',value='20'),pred('c')]})['metrics'][0]
        self.assertEqual((m['tp'],m['fp'],m['fn']),(1,2,1))
        self.assertEqual((m['precision_numerator'],m['precision_denominator'],m['recall_numerator'],m['recall_denominator']),(1,3,1,2))
    def test_no_blind_score(self):
        m=score(labels(item()),{'items':[pred()]})
        self.assertFalse(m['is_independent_evaluation']);self.assertIsNone(m['blind_quality_estimate'])

class EvidenceIntegrity(unittest.TestCase):
    def setUp(self):
        self.output={'layout':[{'file':'x.pdf','sha256':'a'*64,'pages':[{'page':1,'text':'abc СРО обязательно'}]}],
                     'fast_dev2':{'facts':[{'evidence':{'file':'x.pdf','source_sha256':'a'*64,'page':1,
                       'normalized_span':[4,7],'match':'СРО','quote':'abc СРО обязательно','bbox':[1.0,2.0,3.0,4.0]}}]}}
    def test_pass(self):self.assertTrue(audit(self.output)['pass'])
    def test_bad_sha(self):
        d=copy.deepcopy(self.output);d['fast_dev2']['facts'][0]['evidence']['source_sha256']='b'*64
        self.assertEqual(audit(d)['errors'][0]['error'],'sha_mismatch')
    def test_bad_span(self):
        d=copy.deepcopy(self.output);d['fast_dev2']['facts'][0]['evidence']['normalized_span']=[0,3]
        self.assertEqual(audit(d)['errors'][0]['error'],'span_mismatch')
    def test_bad_page(self):
        d=copy.deepcopy(self.output);d['fast_dev2']['facts'][0]['evidence']['page']=3
        self.assertEqual(audit(d)['errors'][0]['error'],'invalid_page')
    def test_bad_bbox(self):
        d=copy.deepcopy(self.output);d['fast_dev2']['facts'][0]['evidence']['bbox']=[3,2,1,4]
        self.assertEqual(audit(d)['errors'][0]['error'],'invalid_bbox')
    def test_missing_doc(self):
        d=copy.deepcopy(self.output);d['layout']=[]
        self.assertEqual(audit(d)['errors'][0]['error'],'missing_document')
    def test_bad_quote(self):
        d=copy.deepcopy(self.output);d['fast_dev2']['facts'][0]['evidence']['quote']='unrelated'
        self.assertEqual(audit(d)['errors'][0]['error'],'invalid_quote')

class SyntheticSmoke(unittest.TestCase):
    def test_reproducible_dev(self):
        from qa.dev_run import run
        root=Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as d:
            run(root/'examples/fast_dev3_conflict_pack',Path(d))
            s=json.loads((Path(d)/'DEV_SUMMARY.json').read_text('utf-8'))
            m=json.loads((Path(d)/'DEV_METRICS.json').read_text('utf-8'))
            self.assertEqual((s['facts'],s['questions'],s['matches']),(9,3,9))
            self.assertFalse(m['is_independent_evaluation'])
    def test_foreign_pdf_refused(self):
        from qa.dev_run import run
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'dev_only_three_expected'):run(Path(d),Path(d)/'out')

if __name__=='__main__':unittest.main()
