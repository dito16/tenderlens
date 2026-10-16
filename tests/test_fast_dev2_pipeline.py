"""FAST DEV 2 regression: real typed candidate structures; zero blind/G4 corpus."""
from __future__ import annotations
import hashlib
import unittest
from tender_screen.domain_pipeline import build_domain_pipeline, _quantity


def doc(text, name='dev.pdf'):
    return {'file':name,'sha256':hashlib.sha256(text.encode()).hexdigest(),
            'page_count':1, 'pages':[{'page':1,'text':text,'words':[],'tables':[]}]}


def pick(text, kind, name='dev.pdf'):
    r=build_domain_pipeline([doc(text,name)])
    return [f for f in r['facts'] if f['kind']==kind]


class WorkScopes(unittest.TestCase):
    def test_construction_work(self):
        x=pick('Ведомость объемов работ: ремонт 125,50 м2.', 'work_scope')[0]
        self.assertEqual((x['value'],x['scope_kind']),('125.50','construction_work'))
    def test_goods(self):
        x=pick('Спецификация: Поставка мебели 30 шт.', 'work_scope')[0]
        self.assertEqual((x['value'],x['scope_kind']),('30','goods'))
    def test_services(self):
        x=pick('Количество: оказание услуг уборки 3 500 м2.', 'work_scope')[0]
        self.assertEqual((x['value'],x['scope_kind']),('3500','service'))
    def test_mixed_is_review(self):
        x=pick('Ведомость объемов: услуги и ремонт 12 м2.', 'work_scope')[0]
        self.assertTrue(x['review_required']); self.assertEqual(x['scope_kind'],'mixed_or_unknown')
    def test_no_unanchored_qty(self):
        self.assertEqual(pick('Кровля составляет 50 м2.', 'work_scope'),[])
    def test_no_budget_conflation(self):
        self.assertEqual(pick('Цена договора: 4 500 000 руб.', 'work_scope'),[])
    def test_no_unit_free_qty(self):
        self.assertEqual(pick('Ведомость объемов работ: 500.', 'work_scope'),[])
    def test_invalid_qty(self):
        self.assertIsNone(_quantity('0'))
        self.assertIsNone(_quantity('10000000000'))
    def test_fraction_units(self):
        self.assertEqual(pick('Дефектная ведомость: монтаж трубопровода 7,125 м3.', 'work_scope')[0]['value'],'7.125')
    def test_table_without_line_context_is_unknown(self):
        self.assertTrue(pick('Количество 30 шт.', 'work_scope')[0]['review_required'])
    def test_scope_evidence_span(self):
        t='Ведомость объемов работ: ремонт 70 м2.'
        row=pick(t,'work_scope')[0];a,b=row['evidence']['normalized_span']
        self.assertEqual(t[a:b],row['evidence']['match']);self.assertIsNone(row['evidence']['bbox'])


class Deadlines(unittest.TestCase):
    def test_numeric_date_with_time(self):
        x=pick('Срок подачи заявок не позднее 23.11.2026 в 15:30.', 'submission_deadline')[0]
        self.assertEqual((x['value'],x['clock'],x['timezone']),('2026-11-23','15:30','unknown'))
    def test_date_in_words(self):
        self.assertEqual(pick('Прием заявок до 9 декабря 2026 года.', 'submission_deadline')[0]['value'],'2026-12-09')
    def test_invalid_date(self):
        self.assertEqual(pick('Срок подачи заявок до 31 февраля 2026 года.', 'submission_deadline'),[])
    def test_random_date_rejected(self):
        self.assertEqual(pick('Документ составлен 23.11.2026. Подпись секретаря.', 'submission_deadline'),[])
    def test_no_cross_sentence(self):
        self.assertEqual(pick('Срок подачи заявок не установлен. Смета 23.11.2026.', 'submission_deadline'),[])
    def test_invalid_clock(self):
        self.assertEqual(pick('Срок подачи заявок до 23.11.2026 в 25:60.', 'submission_deadline'),[])
    def test_old_revision_review(self):
        self.assertTrue(pick('Цитата старой редакции: срок подачи заявок до 23.11.2026.', 'submission_deadline')[0]['review_required'])
    def test_by_boundary(self):
        self.assertEqual(pick('Завершение подачи заявок по 07.12.2026.', 'submission_deadline')[0]['boundary'],'по')


class DurationsAndPayments(unittest.TestCase):
    def test_delivery_and_scheme_not_merged(self):
        rows=pick('Срок поставки товара 9 рабочих дней после подписания договора. Срок подготовки схемы 4 календарных дня.', 'term_duration')
        self.assertEqual({(x['term_kind'],x['value'],x['unit']) for x in rows},
                         {('delivery','9','work_days'),('scheme_preparation','4','calendar_days')})
    def test_request_not_delivery(self):
        self.assertEqual(pick('Срок выполнения заявки 6 рабочих дней.', 'term_duration')[0]['term_kind'],'request_sla')
    def test_work_duration(self):
        self.assertEqual(pick('Срок выполнения работ 45 календарных дней.', 'term_duration')[0]['term_kind'],'work_execution')
    def test_no_unspecified_day_conversion(self):
        x=pick('Срок поставки 4 дня.', 'term_duration')[0]
        self.assertEqual(x['unit'],'days_unspecified');self.assertTrue(x['review_required'])
    def test_payment_10_workdays(self):
        x=pick('Оплата осуществляется в течение 10 рабочих дней после подписания акта.', 'payment_delay')[0]
        self.assertEqual((x['value'],x['unit']),('10','work_days'))
        self.assertIn('акта',x['trigger'])
    def test_qty_not_payment(self):
        self.assertEqual(pick('Спецификация: мебель 30 шт.', 'payment_delay'),[])
    def test_payment_no_context(self):
        self.assertEqual(pick('В течение 10 рабочих дней после подписания акта.', 'payment_delay'),[])
    def test_no_cross_sentence_payment(self):
        self.assertEqual(pick('Оплата не предусмотрена. Поставка в течение 10 рабочих дней.', 'payment_delay'),[])
    def test_no_advance(self):
        self.assertEqual(pick('Аванс не предусмотрен.', 'advance')[0]['polarity'],'explicit_negative')
    def test_advance_mention_review(self):
        self.assertTrue(pick('Порядок выдачи аванса описан в приложении.', 'advance')[0]['review_required'])
    def test_no_cross_date_borrowing(self):
        self.assertEqual(pick('Срок поставки не указан. Оплата 10 рабочих дней.', 'term_duration'),[])


class WarrantyAndRequirements(unittest.TestCase):
    def test_warranty_work_vs_materials(self):
        rows=pick('Гарантийный срок на работы составляет 36 месяцев. Гарантийный срок на материалы составляет 12 месяцев.', 'warranty')
        self.assertEqual({(x['warranty_subject'],x['value']) for x in rows},{('works','36'),('materials','12')})
    def test_unknown_warranty_review(self):
        self.assertTrue(pick('Гарантийный срок составляет 24 месяца.', 'warranty')[0]['review_required'])
    def test_no_warranty_from_product_price(self):
        self.assertEqual(pick('Гарантия производителя не установлена. Оплата 36 месяцев.', 'warranty'),[])
    def test_sro_negation(self):
        self.assertEqual(pick('Членство в СРО не требуется.', 'sro_requirement')[0]['value'],'explicit_negative')
    def test_sro_positive(self):
        self.assertEqual(pick('Членство в СРО обязательно.', 'sro_requirement')[0]['value'],'explicit_positive')
    def test_sro_mention_only(self):
        self.assertTrue(pick('Информация об СРО.', 'sro_requirement')[0]['review_required'])
    def test_sro_historical(self):
        self.assertEqual(pick('Цитата старой редакции: членство в СРО требуется.', 'sro_requirement')[0]['value'],'historical_or_quoted')
    def test_site_positive(self):
        self.assertEqual(pick('Осмотр объекта обязателен.', 'site_visit_requirement')[0]['value'],'explicit_positive')
    def test_site_negative(self):
        self.assertEqual(pick('Осмотр объекта не обязателен.', 'site_visit_requirement')[0]['value'],'explicit_negative')
    def test_sro_conditional_not_absolute(self):
        row=pick('Членство в СРО требуется только при выполнении особых работ.', 'sro_requirement')[0]
        self.assertEqual(row['value'],'conditional_or_exception')
        self.assertTrue(row['review_required'])
    def test_sro_exception_not_negative_absolute(self):
        row=pick('Членство в СРО не требуется, кроме опасных строительных работ.', 'sro_requirement')[0]
        self.assertEqual(row['value'],'conditional_or_exception')
    def test_sro_no_eligibility_from_reference(self):
        row=pick('Справочная информация об СРО.', 'sro_requirement')[0]
        self.assertEqual(row['value'],'mention_only')

    def test_sro_and_site_different(self):
        t='Членство в СРО не требуется. Осмотр объекта обязателен.'
        self.assertEqual(pick(t,'sro_requirement')[0]['value'],'explicit_negative')
        self.assertEqual(pick(t,'site_visit_requirement')[0]['value'],'explicit_positive')
    def test_wrong_page_evidence_rejected(self):
        t='Срок подачи заявок до 23.11.2026.'
        d=doc(t)
        r=build_domain_pipeline([d])
        self.assertEqual(len(r['facts']),1)
        self.assertEqual(r['facts'][0]['evidence']['source_sha256'],d['sha256'])
    def test_multi_doc_conflict_not_resolved(self):
        a=doc('Срок подачи заявок до 23.11.2026.','a.pdf')
        b=doc('Срок подачи заявок до 09.12.2026.','b.pdf')
        r=build_domain_pipeline([a,b])
        self.assertEqual(len(r['possible_conflicts']),1)
        self.assertEqual(r['possible_conflicts'][0]['kind'],'submission_deadline')
    def test_date_not_convert_to_local_clock(self):
        x=pick('Подача заявок до 09.12.2026 в 10:00.', 'submission_deadline')[0]
        self.assertEqual(x['timezone'],'unknown')

class NativeQuantityCells(unittest.TestCase):
    def test_quantity_separate_unit_cell(self):
        t='Ведомость объемов работ'
        d=doc(t)
        d['pages'][0]['tables']=[{'row_count':2,'cells':[
            {'row':0,'column':0,'value':'Наименование','bbox':[0,0,100,20]},
            {'row':0,'column':1,'value':'Количество','bbox':[100,0,180,20]},
            {'row':0,'column':2,'value':'Ед. изм.','bbox':[180,0,250,20]},
            {'row':1,'column':0,'value':'Ремонт кровли','bbox':[0,20,100,40]},
            {'row':1,'column':1,'value':'125,5','bbox':[100,20,180,40]},
            {'row':1,'column':2,'value':'м2','bbox':[180,20,250,40]}]}]
        result=build_domain_pipeline([d]);r=result['facts'][0]
        self.assertEqual((r['value'],r['unit'],r['scope_kind']),('125.5','м2','construction_work'))
        self.assertEqual(r['evidence']['basis'],'native_table_cells')
        self.assertEqual(r['evidence']['value_cell'],[1,1])
    def test_quantity_inline_unit_table(self):
        d=doc('')
        d['pages'][0]['tables']=[{'row_count':2,'cells':[
            {'row':0,'column':0,'value':'Количество'},
            {'row':1,'column':0,'value':'18 м3'}]}]
        r=build_domain_pipeline([d])['facts'][0]
        self.assertEqual((r['value'],r['unit']),('18','м3'))
    def test_table_no_quantity_header(self):
        d=doc('')
        d['pages'][0]['tables']=[{'row_count':2,'cells':[
            {'row':0,'column':0,'value':'Цена'},
            {'row':1,'column':0,'value':'18 м2'}]}]
        self.assertEqual(build_domain_pipeline([d])['facts'],[])
    def test_table_quantity_without_unit_rejected(self):
        d=doc('')
        d['pages'][0]['tables']=[{'row_count':2,'cells':[
            {'row':0,'column':0,'value':'Количество'},
            {'row':1,'column':0,'value':'18'}]}]
        self.assertEqual(build_domain_pipeline([d])['facts'],[])
    def test_tampered_table_cell_rejected_by_validator(self):
        from tender_screen.domain_pipeline import validate_pipeline
        d=doc('')
        d['pages'][0]['tables']=[{'row_count':2,'cells':[
            {'row':0,'column':0,'value':'Количество'},
            {'row':1,'column':0,'value':'18 м2'}]}]
        r=build_domain_pipeline([d]);r['facts'][0]['evidence']['match']='20 м2'
        rejected=[]
        self.assertEqual(validate_pipeline([d],r['facts'],rejected),[])
        self.assertEqual(rejected[0]['reason'],'native_cell_value_changed')

if __name__=='__main__': unittest.main()
