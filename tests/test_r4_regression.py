"""R4 precision-oriented independent wording and evidence regressions.

Real external PDFs are not embedded in the distributable source. These synthetic
clauses include counterfactuals to guard against overfitting to R3.
"""
from __future__ import annotations
import hashlib
import unittest
from tender_screen.real_terms import extract_terms
from tender_screen.context import classify
from tender_screen.core import analyze


def fake(text: str, name='synthetic.pdf'):
    return {'file': name, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
            'page_count': 1,
            'pages': [{'page': 1, 'text': text, 'raw_text': text,
                       'normalized_text': text, 'has_text': bool(text)}]}


def term(text: str, key: str):
    return extract_terms([fake(text)])[key]


class R4WordingRegressions(unittest.TestCase):
    def assert_found(self, text, key, value, unit=None):
        t = term(text, key)
        self.assertEqual(t['status'], 'extracted', (key, t))
        self.assertEqual(t['value'], value)
        if unit:
            self.assertEqual(t['unit'], unit)
        for row in t['candidates']:
            ev = row['evidence']; a,b = ev['normalized_span']
            self.assertEqual(text[a:b], ev['match'])
            self.assertEqual(ev['page'], 1)
        return t

    def assert_absent(self, text, key):
        self.assertEqual(term(text, key)['status'], 'not-found', (key,text))

    def test_subject_named_services(self):
        self.assert_found('Номер извещения 28-2025 Наименование Оказание услуг технической поддержки системе 1С ЗУП закупки Способ проведения Закупка путем переговоров',
                          'scope', 'Оказание услуг технической поддержки системе 1С ЗУП')

    def test_subject_name_interleaved_between_words(self):
        self.assert_found('Номер извещения 58-2025 Оказание услуг по обслуживанию пожарной Наименование сигнализации закупки Способ проведения закупки',
                          'scope', 'Оказание услуг по обслуживанию пожарной сигнализации')

    def test_subject_short_goods(self):
        self.assert_found('Номер извещения 43-2025 Наименование Поставка товаров закупки Способ проведения закупки',
                          'scope', 'Поставка товаров')

    def test_subject_goods_with_parentheses(self):
        self.assert_found('Наименование Поставка товара (питьевая вода) закупки Способ проведения закупки',
                          'scope', 'Поставка товара (питьевая вода)')

    def test_subject_services_from_table(self):
        self.assert_found('Наименование Оказание услуг по обработке и доставке отправлений закупки Способ проведения закупки',
                          'scope', 'Оказание услуг по обработке и доставке отправлений')

    def test_subject_from_contract_header(self):
        self.assert_found('(проект) КОНТРАКТ № 10 на выполнение работ по ремонту санитарных узлов школы ИКЗ 2000000000',
                          'scope', 'на выполнение работ по ремонту санитарных узлов школы')

    def test_subject_does_not_assume_scope_from_generic_text(self):
        self.assert_absent('Оказание услуг по наладке. Коммерческое предложение зафиксировано.', 'scope')

    def test_subject_no_generic_heading(self):
        self.assert_absent('Наименование закупки Техническое задание Способ проведения', 'scope')

    def test_subject_one_field_not_duplicate_table_sections(self):
        t=term('Номер извещения 20-2025 Наименование Оказание услуг по обучению персонала закупки Способ проведения. Наименование услуги Оказание услуг по обучению персонала.', 'scope')
        self.assertEqual(t['status'], 'extracted')
        self.assertEqual(len(t['candidates']),1)

    def test_end_date_after_work_label(self):
        self.assert_found('Срок выполнения работ: с даты подписания договора до 30 декабря 2026 года.',
                          'work_end_date', '2026-12-30', 'date')

    def test_end_date_after_supply_label(self):
        self.assert_found('Срок поставки товара: с 12 января 2026 года по 30 декабря 2026 года.',
                          'work_end_date', '2026-12-30', 'date')

    def test_end_date_after_service_label(self):
        self.assert_found('Срок оказания услуг С момента подписания договора до 31 декабря 2025 года.',
                          'work_end_date', '2025-12-31', 'date')

    def test_end_date_before_label_in_reordered_table(self):
        self.assert_found('С 01.01.2026 по 31.12.2026 Срок оказания услуг',
                          'work_end_date', '2026-12-31', 'date')

    def test_end_date_numeric_not_later(self):
        self.assert_found('Окончание выполнения работ: не позднее 17.11.2025 г.',
                          'work_end_date', '2025-11-17', 'date')

    def test_end_date_not_proposal_deadline(self):
        self.assert_absent('Просим направить коммерческое предложение до 31 декабря 2025 года.', 'work_end_date')

    def test_end_date_not_guessed_from_unrelated_calendar_date(self):
        self.assert_absent('Составлен акт 31 декабря 2025 года. Договор на обслуживание.', 'work_end_date')

    def test_end_date_invalid_calendar(self):
        self.assert_absent('Срок поставки товара по 31 февраля 2026 года.', 'work_end_date')

    def test_end_date_must_not_cross_sentences(self):
        self.assert_absent('Срок оказания услуг пока не определён. Просим направить предложение до 30 декабря 2026 года.', 'work_end_date')

    def test_warranty_on_services(self):
        self.assert_found('Гарантия на оказанные услуги – 12 месяцев с даты подписания акта.',
                          'warranty', '12', 'months')

    def test_warranty_tabular_short(self):
        self.assert_found('Гарантийный Не менее 12 месяцев срок',
                          'warranty', '12', 'months')

    def test_warranty_long_phrase_and_written_number(self):
        self.assert_found('Гарантийный срок на работы исчисляется с даты подписания Заказчиком документа о приемке работ и составляет 36 (тридцать шесть) месяцев.',
                          'warranty', '36', 'months')

    def test_warranty_ordinary_sentence(self):
        self.assert_found('Гарантийный срок на выполняемые работы составляет 12 месяцев.',
                          'warranty', '12', 'months')

    def test_warranty_not_a_product_claim(self):
        self.assert_absent('Исполнитель гарантирует соответствие требованиям ГОСТ.', 'warranty')

    def test_warranty_not_per_producer_ambiguous(self):
        self.assert_absent('Гарантийный срок на материалы – не менее срока производителя.', 'warranty')

    def test_warranty_no_cross_sentence(self):
        self.assert_absent('Гарантийный срок не установлен. Оплата в течение 12 месяцев.', 'warranty')

    def test_request_service_after_acceptance(self):
        self.assert_found('Срок оказания 10 (десять) рабочих дней с момента принятия Исполнителем Заявки от Заказчика',
                          'request_completion_sla', '10', 'work_days')

    def test_request_goods_after_application(self):
        self.assert_found('Срок поставки товара составляет три рабочих дня со дня получения поставщиком заявки от заказчика.',
                          'request_completion_sla', '3', 'work_days')

    def test_request_no_application(self):
        self.assert_absent('Срок оказания услуг 10 рабочих дней с момента подписания договора.', 'request_completion_sla')

    def test_request_no_payment_confusion(self):
        self.assert_absent('Оплата в течение 10 рабочих дней с даты подписания акта по заявке.', 'request_completion_sla')

    def test_request_not_transport_notification(self):
        self.assert_absent('Поставщик сообщает о доставке товара за один рабочий день до доставки.', 'request_completion_sla')

    def test_request_no_cross_sentence(self):
        self.assert_absent('Срок оказания услуг 10 рабочих дней со дня подписания договора. Заявки присылает заказчик.', 'request_completion_sla')

    def test_sro_negative_in_mixed_licenses_clause(self):
        s='Необходимость наличия лицензий, членства в СРО: не предусмотрено.'
        a=s.index('СРО')
        self.assertEqual(classify('sro',s,a,a+3)[0], 'explicit_negative')
        r=analyze([fake(s)])
        self.assertNotIn('Условие о СРО',[x['title'] for x in r['findings']])
        self.assertIn('sro_context',[x['id'] for x in r['findings']])

    def test_sro_design_material_reference_not_positive_requirement(self):
        r=analyze([fake('Состав проектной документации: Выписка СРО, раздел ПЗ.')])
        f=next(x for x in r['findings'] if x['id']=='sro')
        self.assertEqual(f['kind'],'info')
        self.assertIn('обязательность не подтверждена',f['title'])

    def test_sro_positive_explicit_requirement_remains(self):
        r=analyze([fake('Членство в СРО требуется для выполнения работ.')])
        f=next(x for x in r['findings'] if x['id']=='sro')
        self.assertEqual(f['kind'],'requirement')
        self.assertIn('Требование',f['title'])


if __name__=='__main__':
    unittest.main()
