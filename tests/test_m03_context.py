"""M03 adversarial, standalone source-literal oracles, no customer content."""
import hashlib
import unittest
from tender_screen.core import analyze
from tender_screen.context import advance_conditions, classify, sentence, clause_conditions


def doc(file,text):
    return {'file':file,'sha256':hashlib.sha256((file+text).encode()).hexdigest(),
            'page_count':1,'pages':[{'page':1,'text':text,'raw_text':text,'has_text':bool(text)}]}


def findings(r, id):
    return [f for f in r['findings'] if f['id']==id]


class ContextGoldenTests(unittest.TestCase):
    def test_01_distinct_docs_explicit_advance_conflict(self):
        docs=[doc('a.pdf','Предусмотрен аванс 20%.'),doc('b.pdf','Аванс не предусмотрен.')]
        r=analyze(docs)
        self.assertEqual(len(r['conflicts']),1)
        c=r['conflicts'][0]
        self.assertEqual((c['family'],c['status']),('advance_terms','needs-review'))
        self.assertTrue(c['human_review_required'])
        self.assertEqual({e['file'] for e in c['evidence']},{'a.pdf','b.pdf'})
        self.assertEqual(len(c['evidence_ids']),2)
        for e in c['evidence']:
            self.assertEqual(e['source_sha256'],next(x['sha256'] for x in docs if x['file']==e['file']))
            self.assertEqual(e['page'],1)
            a,b=e['normalized_span']
            self.assertEqual(next(x for x in docs if x['file']==e['file'])['pages'][0]['text'][a:b],e['match'])

    def test_02_no_cross_doc_conflict_when_same_file(self):
        r=analyze([doc('single.pdf','Аванс 20%. Аванс не предусмотрен.')])
        self.assertFalse(r['conflicts'])
        self.assertFalse(findings(r,'advance_conflict'))

    def test_03_negated_percent_is_not_positive_advance(self):
        r=analyze([doc('a.pdf','Аванс 20% НЕ предусмотрен.'),
                   doc('b.pdf','Аванс отсутствует.')])
        self.assertFalse(r['conflicts'])
        self.assertNotIn('explicit_positive',[x['polarity'] for x in r['conditions'] if x['family']=='advance_terms'])
        self.assertEqual(r['typed_fields']['advance_percent']['status'],'ambiguous')

    def test_04_retention_negation_no_positive_signal(self):
        r=analyze([doc('a.pdf','Удержание 5% не предусмотрено.')])
        self.assertFalse(findings(r,'retention'))
        self.assertTrue(findings(r,'retention_context'))
        self.assertEqual(findings(r,'retention_context')[0]['kind'],'info')
        self.assertEqual(next(x for x in r['conditions'] if x['family']=='retention_terms')['polarity'],'explicit_negative')

    def test_05_unpriced_changes_negated_not_risk(self):
        r=analyze([doc('a.pdf','Работы без дополнительной оплаты не производятся.')])
        self.assertFalse(findings(r,'unpriced_changes'))
        self.assertEqual(findings(r,'unpriced_changes_context')[0]['kind'],'info')

    def test_short_without_extra_pay_negated(self):
        r=analyze([doc('a.pdf','Работы без доплаты не производятся.')])
        self.assertFalse(findings(r,'unpriced_changes'))
        self.assertEqual(findings(r,'unpriced_changes_context')[0]['kind'],'info')

    def test_06_real_unpriced_changes_is_risk(self):
        r=analyze([doc('a.pdf','Дополнительные работы выполняются без увеличения цены договора.')])
        self.assertEqual(findings(r,'unpriced_changes')[0]['kind'],'risk')

    def test_07_sro_not_required_is_not_requirement(self):
        r=analyze([doc('a.pdf','СРО не требуется.')])
        self.assertFalse(findings(r,'sro'))
        self.assertEqual(findings(r,'sro_context')[0]['kind'],'info')
        self.assertEqual(next(x for x in r['conditions'] if x['family']=='sro_wording')['polarity'],'explicit_negative')

    def test_08_conditional_sro_review_not_eligibility(self):
        r=analyze([doc('a.pdf','Для допуска требуется членство в СРО, если применимо.')])
        self.assertFalse(findings(r,'sro'))
        self.assertTrue(findings(r,'sro_context'))
        self.assertEqual(findings(r,'sro_context')[0]['kind'],'review')

    def test_09_old_revision_not_live_conflict(self):
        r=analyze([doc('a.pdf','В прежней редакции аванс не предусмотрен.'),
                   doc('b.pdf','Предусмотрен аванс 20%.')])
        self.assertFalse(r['conflicts'])
        self.assertTrue(any(c['polarity']=='unclear' for c in r['conditions']))
        self.assertTrue(any('старой редакции' in x for x in r['issues']))

    def test_10_quoted_negation_not_live_conflict(self):
        r=analyze([doc('a.pdf','Цитата из договора: аванс не предусмотрен.'),
                   doc('b.pdf','Аванс 10%.')])
        self.assertFalse(r['conflicts'])

    def test_11_no_keyword_no_conflict_and_unknown(self):
        r=analyze([doc('a.pdf','Поставка материалов производится по графику.')])
        self.assertFalse(r['conflicts'])
        self.assertEqual(r['typed_fields']['advance_percent']['status'],'not-found')

    def test_12_ks_forms_negated_not_asserted_required(self):
        r=analyze([doc('a.pdf','Формы КС-2 и КС-3 не применяются.')])
        self.assertFalse(findings(r,'closeout'))
        self.assertEqual(findings(r,'closeout_context')[0]['kind'],'info')

    def test_13_unrelated_sentence_negation_does_not_cancel_risk(self):
        r=analyze([doc('a.pdf','Работы выполняются без увеличения цены. Другие операции не производятся.')])
        self.assertTrue(findings(r,'unpriced_changes'))

    def test_14_positive_retention_stays_review(self):
        r=analyze([doc('a.pdf','Удержание 5% предусмотрено до завершения работ.')])
        self.assertEqual(findings(r,'retention')[0]['kind'],'review')

    def test_15_three_docs_unknown_do_not_create_false_conflict(self):
        r=analyze([doc('a.pdf','Аванс 20%.'),doc('b.pdf','Аванс упомянут.'),
                   doc('c.pdf','В старой редакции аванс не предусмотрен.')])
        self.assertFalse(r['conflicts'])

    def test_16_two_runs_same_ids(self):
        docs=[doc('one.pdf','Аванс 20%.'),doc('two.pdf','Аванс не предусмотрен.')]
        self.assertEqual(analyze(docs)['conflicts'],analyze(docs)['conflicts'])

    def test_17_no_automatic_compliance_or_legal_decision(self):
        r=analyze([doc('sro.pdf','Наличие СРО обязательно.')])
        self.assertIn('ЧЕЛОВЕКА',r['decision'])
        self.assertIn('юридическим', r['disclaimer'])
        self.assertFalse(any(k in r for k in ('legal_compliance_score','fraud_score','bid_probability')))

    def test_18_site_visit_explicit_negative_as_reference(self):
        r=analyze([doc('a.pdf','Осмотр объекта не обязателен.')])
        c=next(x for x in r['conditions'] if x['family']=='site_visit')
        self.assertEqual(c['polarity'],'explicit_negative')

    def test_19_scanned_page_no_invented_conflict(self):
        r=analyze([{'file':'scan.pdf','sha256':'a'*64,'page_count':1,
                    'pages':[{'page':1,'text':'','raw_text':'','has_text':False}]}])
        self.assertFalse(r['conflicts'])
        self.assertEqual(r['typed_fields']['advance_percent']['status'],'ocr-required')


if __name__=='__main__':unittest.main()
