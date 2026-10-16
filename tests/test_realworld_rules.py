"""Independent wording regressions for RW-001..RW-007.

The actual 2025 public PDF sources are NOT stored in the release; their exact
checks live in tools/check_realworld.py and in a separate acceptance runner.
"""
import hashlib
import unittest
from tender_screen.core import analyze
from tender_screen.fields import extract_typed_fields
from tender_screen.real_terms import extract_terms


def doc(text, name='fake.pdf'):
    return {'file': name, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
            'page_count': 1, 'pages': [{'page': 1, 'text': text,
             'raw_text': text, 'has_text': bool(text)}]}


class RealWorldPatterns(unittest.TestCase):
    def term(self, text, key):
        return extract_terms([doc(text)])[key]

    def test_offer_deadline_words_with_local_timezone(self):
        t = self.term('Предложение просим направить до 16:00 (мск.врм) 12 декабря 2025 года на электронную почту', 'submission_deadline')
        self.assertEqual((t['status'], t['value']), ('extracted', '2025-12-12'))

    def test_offer_deadline_with_numeric_format(self):
        t = self.term('Приём предложений до 12.12.2025', 'submission_deadline')
        self.assertEqual(t['value'], '2025-12-12')

    def test_unrelated_date_not_promoted_to_offer(self):
        self.assertEqual(self.term('Договор подписан 12 декабря 2025 года.', 'submission_deadline')['status'], 'not-found')

    def test_wrong_calendar_date_rejected(self):
        self.assertEqual(self.term('Просим направить до 14:00 31 февраля 2026 года.', 'submission_deadline')['status'], 'not-found')

    def test_contract_end_date(self):
        self.assertEqual(self.term('Срок выполнения работ: С даты подписания договора до 30 декабря 2026 года.', 'work_end_date')['value'], '2026-12-30')

    def test_contract_end_does_not_imply_duration_days(self):
        r=extract_terms([doc('Срок выполнения работ: С даты подписания договора до 30 декабря 2026 года.')]);
        self.assertEqual(r['work_duration']['status'], 'not-found')

    def test_start_offset_distinct_from_duration(self):
        t = extract_terms([doc('Начальный срок: через 14 рабочих дней с даты подписания договора. Конечный срок: не более 6 месяцев с даты начала работ.')])
        self.assertEqual((t['work_start_offset']['value'],t['work_start_offset']['unit']),('14','work_days'))
        self.assertEqual((t['work_duration']['value'],t['work_duration']['unit']),('6','months'))

    def test_payment_with_numeric_and_word_in_parentheses(self):
        self.assertEqual(self.term('Оплата производится в срок не более 20 (Двадцати) рабочих дней с даты подписания акта.', 'payment_delay')['value'], '20')

    def test_payment_with_common_typo(self):
        self.assertEqual(self.term('Оплата производится в течении 10 (десяти) рабочих дней после акта.', 'payment_delay')['value'], '10')

    def test_unrelated_20_day_period_is_not_payment(self):
        self.assertEqual(self.term('Исполнитель в течение 20 рабочих дней устраняет замечания.', 'payment_delay')['status'], 'not-found')

    def test_site_visit_requires_before_commercial_offer(self):
        t=self.term('Перед подачей коммерческого предложения должно быть осуществлено проведение осмотра помещений.', 'site_visit');
        self.assertEqual(t['status'], 'extracted')

    def test_optional_visit_not_marked_as_prebid_obligation(self):
        t=self.term('Осмотр объекта до подачи заявки возможен, но не обязателен.', 'site_visit')
        self.assertEqual(t['status'], 'not-found')

    def test_warranty_12_months(self):
        t=self.term('Гарантийный срок на выполняемые работы составляет 12 (двенадцать) месяцев с акта.', 'warranty')
        self.assertEqual((t['value'],t['unit']),('12','months'))

    def test_warranty_is_not_general_duration(self):
        terms=extract_terms([doc('Гарантийный срок составляет 12 месяцев.')]);
        self.assertEqual(terms['work_duration']['status'], 'not-found')

    def test_start_and_finish_request_distinct(self):
        s=('Исполнитель в течение двух рабочих дней с момента поступления заявки приступает к ремонтным работам. '
           'Исполнитель обязуется выполнить ремонтные работы по заявке не позднее двух рабочих дней после получения заявки.')
        terms=extract_terms([doc(s)])
        self.assertEqual(terms['request_start_sla']['value'], '2')
        self.assertEqual(terms['request_completion_sla']['value'], '2')
        self.assertEqual(terms['work_duration']['status'], 'not-found')

    def test_start_sla_not_completion(self):
        s='Исполнитель в течение двух рабочих дней после поступления заявки приступает к работам.'
        self.assertEqual(self.term(s, 'request_completion_sla')['status'], 'not-found')

    def test_scope_from_table_like_title(self):
        s='Номер извещения 53-2025 Наименование Выполнение работ по мелкому бытовому ремонту (услуга мастер- закупки универсал) Способ Закупка путем переговоров'
        t=self.term(s,'scope')
        self.assertIn('мелкому бытовому ремонту',t['value'])
        self.assertNotIn('закупки универсал',t['value'])

    def test_scope_not_guessed_from_generic_heading(self):
        self.assertEqual(self.term('Наименование закупки Техническое задание', 'scope')['status'], 'not-found')

    def test_budget_sections_and_percents_do_not_become_candidates(self):
        fields=extract_typed_fields([doc('2. Стоимость Работ и порядок расчетов 2.1. Стоимость Работ по договору составляет ____. Стоимость Работ изменяется не более чем на 50 %')])
        self.assertEqual(fields['budget_rub']['status'],'not-found')
        self.assertEqual(fields['budget_rub']['candidates'],[])

    def test_budget_with_explicit_rubles_still_extracted(self):
        f=extract_typed_fields([doc('Стоимость работ 2 500 000 руб.')])['budget_rub']
        self.assertEqual((f['status'],f['value']),('extracted','2500000'))

    def test_analysis_quality_avoids_false_green_on_no_match(self):
        result=analyze([doc('прочий текст ' * 500)])
        self.assertEqual(result['analysis_quality']['status'],'insufficient_coverage')
        self.assertIn('Низкий охват',result['issues'][0])

    def test_analysis_quality_no_completeness_claim_even_when_found(self):
        result=analyze([doc('Оплата производится в течении 10 (десяти) рабочих дней после акта.')])
        self.assertFalse(result['analysis_quality']['validated_completeness'])

    def test_stable_evidence_offsets(self):
        d=doc('Просим направить до 16:00 12 декабря 2025 года.');t=extract_terms([d])['submission_deadline']
        proof=t['candidates'][0]['evidence'];a,b=proof['normalized_span'];self.assertEqual(d['pages'][0]['text'][a:b],proof['match'])

    def test_no_not_found_values_are_invented(self):
        terms=extract_terms([doc('В проекте отсутствует описание порядка расчетов.')])
        self.assertEqual(terms['payment_delay']['status'],'not-found')
        self.assertIsNone(terms['payment_delay']['value'])


if __name__=='__main__': unittest.main()
