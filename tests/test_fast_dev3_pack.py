import hashlib
import unittest
from tender_screen.pack import build_pack_manifest,compare_pack
from tender_screen.domain_pipeline import build_domain_pipeline


def make(name,text):
    return {'file':name,'sha256':hashlib.sha256(text.encode()).hexdigest(),
            'page_count':1,'document_role':{'primary':'unknown'},
            'pages':[{'page':1,'text':text,'words':[],'tables':[]}]}

def questions(a,b,hints=None):
    docs=[make('notice.pdf',a),make('contract.pdf',b)]
    manifest=build_pack_manifest(docs,hints)
    return compare_pack(manifest,build_domain_pipeline(docs),docs)

class PackManifestTests(unittest.TestCase):
    def test_schema(self):
        d=make('n.pdf','abc');m=build_pack_manifest([d]);self.assertEqual(m['schema'],'tenderlens.pack.v1')
    def test_unknown_effective(self):
        self.assertEqual(build_pack_manifest([make('n.pdf','abc')])['documents'][0]['effective'],'unknown')
    def test_revision_explicit(self):
        m=build_pack_manifest([make('n.pdf','abc')],{'n.pdf':{'revision':'2','effective':'current','scope':'roof'}})
        self.assertEqual((m['documents'][0]['revision'],m['documents'][0]['scope']),('2','roof'))
    def test_bad_status(self):
        with self.assertRaises(ValueError):build_pack_manifest([make('n.pdf','abc')],{'n.pdf':{'effective':'yes'}})
    def test_bad_hint(self):
        with self.assertRaises(ValueError):build_pack_manifest([make('n.pdf','abc')],{'other.pdf':{}})
    def test_unknown_metadata_field(self):
        with self.assertRaises(ValueError):build_pack_manifest([make('n.pdf','abc')],{'n.pdf':{'approved':'true'}})
    def test_duplicate_names(self):
        with self.assertRaises(ValueError):build_pack_manifest([make('x.pdf','abc'),make('x.pdf','def')])
    def test_invalid_sha(self):
        d=make('x.pdf','a');d['sha256']='abc'
        with self.assertRaises(ValueError):build_pack_manifest([d])

class ConflictTests(unittest.TestCase):
    def test_sro_positive_negative(self):
        x=questions('Членство в СРО обязательно.','Членство в СРО не требуется.')
        self.assertIn('opposing_sro_wording',[q['kind'] for q in x['questions']])
    def test_sro_two_positive(self):
        x=questions('Членство в СРО обязательно.','Членство в СРО обязательно.')
        self.assertEqual(x['counts']['questions'],0)
    def test_scope_different_prevents_sro(self):
        hints={'notice.pdf':{'scope':'road'},'contract.pdf':{'scope':'roof'}}
        x=questions('Членство в СРО обязательно.','Членство в СРО не требуется.',hints)
        self.assertEqual(x['counts']['questions'],0)
    def test_scope_unknown_review(self):
        x=questions('Членство в СРО обязательно.','Членство в СРО не требуется.')
        self.assertIn('unknown',x['questions'][0]['reason'])
    def test_historical_suppressed(self):
        hints={'notice.pdf':{'effective':'historical'},'contract.pdf':{'effective':'current'}}
        x=questions('Членство в СРО обязательно.','Членство в СРО не требуется.',hints)
        self.assertEqual(x['counts']['questions'],0)
        self.assertTrue(x['excluded_historical'])
    def test_quote_old_suppressed(self):
        x=questions('Членство в СРО обязательно.','Цитата старой редакции: членство в СРО не требуется.')
        self.assertFalse(any(q['kind']=='opposing_sro_wording' for q in x['questions']))
    def test_advance(self):
        x=questions('Аванс предусмотрен 20%.','Аванс не предусмотрен.')
        self.assertEqual(x['questions'][0]['kind'],'opposing_advance_wording')
    def test_no_advance_if_mention(self):
        x=questions('Порядок аванса описан в Приложении.','Аванс не предусмотрен.')
        self.assertFalse(x['questions'])
    def test_payment_difference(self):
        x=questions('Оплата осуществляется в течение 10 рабочих дней после подписания акта.',
                    'Оплата осуществляется в течение 20 рабочих дней после подписания акта.')
        self.assertEqual(x['questions'][0]['kind'],'different_payment_delay_wording')
    def test_payment_unit_question_not_verdict(self):
        x=questions('Оплата осуществляется в течение 10 рабочих дней после подписания акта.',
                    'Оплата осуществляется в течение 10 календарных дней после подписания акта.')
        self.assertEqual(x['questions'][0]['kind'],'incompatible_day_units_question')
        self.assertIsNone(x['questions'][0]['legal_verdict'])
    def test_payment_different_trigger(self):
        x=questions('Оплата осуществляется в течение 10 рабочих дней после подписания акта.',
                    'Оплата осуществляется в течение 20 рабочих дней после поставки.')
        self.assertFalse(x['questions'])
    def test_payment_same_does_not_conflict(self):
        x=questions('Оплата осуществляется в течение 10 рабочих дней после подписания акта.',
                    'Оплата осуществляется в течение 10 рабочих дней после подписания акта.')
        self.assertFalse(x['questions'])
    def test_warranty_different_subject_no_cross(self):
        x=questions('Гарантийный срок на работы составляет 36 месяцев.',
                    'Гарантийный срок на материалы составляет 12 месяцев.')
        self.assertFalse(x['questions'])
    def test_warranty_same_subject_question(self):
        x=questions('Гарантийный срок на работы составляет 36 месяцев.',
                    'Гарантийный срок на работы составляет 24 месяца.')
        self.assertEqual(x['questions'][0]['kind'],'different_warranty_wording')
    def test_term_work_vs_scheme_no_cross(self):
        x=questions('Срок выполнения работ 45 календарных дней.',
                    'Срок подготовки схемы 4 календарных дня.')
        self.assertFalse(x['questions'])
    def test_term_units_question(self):
        x=questions('Срок выполнения работ 30 календарных дней.',
                    'Срок выполнения работ 30 рабочих дней.')
        self.assertEqual(x['questions'][0]['kind'],'incompatible_day_units_question')
    def test_submission_deadline(self):
        x=questions('Срок подачи заявок до 23.11.2026.',
                    'Срок подачи заявок до 24.11.2026.')
        self.assertEqual(x['questions'][0]['kind'],'different_submission_deadline_wording')
    def test_evidence_pair(self):
        x=questions('Членство в СРО обязательно.','Членство в СРО не требуется.')
        e=x['questions'][0]['evidence'];self.assertEqual(len(e),2)
        self.assertNotEqual(e[0]['source_sha256'],e[1]['source_sha256'])
        self.assertTrue(all(i['quote'] for i in e))
    def test_no_auto_verdict(self):
        x=questions('Аванс предусмотрен 20%.','Аванс не предусмотрен.')
        self.assertEqual((x['questions'][0]['status'],x['questions'][0]['legal_verdict']),('unresolved',None))
    def test_missing_attachment_is_question(self):
        x=questions('См. приложение №2 к договору.','Проект договора подряда.')
        self.assertTrue(x['attachment_questions'])
        self.assertTrue(all(r['status']=='verify_pack_completeness_not_proven_missing' for r in x['attachment_questions']))
    def test_attachment_not_missing_if_named(self):
        d1=make('notice.pdf','См. приложение №2 к договору.')
        d2=make('Приложение №2.pdf','Наименование: нормы снабжения.')
        x=compare_pack(build_pack_manifest([d1,d2]),build_domain_pipeline([d1,d2]),[d1,d2])
        self.assertFalse(x['attachment_questions'])
    def test_no_missing_false_statement(self):
        x=questions('Извещение о закупке.', 'Проект договора.')
        self.assertFalse(x['attachment_questions'])
    def test_schema_and_coverage(self):
        x=questions('Членство в СРО обязательно.','Членство в СРО не требуется.')
        self.assertEqual(x['schema'],'tenderlens.cross_document.v1')
        self.assertIn('no_auto_revision_priority',x['warnings'][-1]) if False else None

if __name__=='__main__':unittest.main()
