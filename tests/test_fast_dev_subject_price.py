"""M03: strict typed prices and subjects, no silent joins across roles."""
import hashlib
import unittest
from tender_screen.subject_price import build_normalized_card, parse_rub_amount


def doc(text, filename='synthetic.pdf'):
    return {'file': filename, 'sha256':hashlib.sha256(text.encode()).hexdigest(),
            'pages':[{'page':1,'text':text,'has_text':bool(text),'words':[]}]}


class SubjectMoneyTests(unittest.TestCase):
    def test_four_currency_representations(self):
        for s in ['1 234 567,89 рублей','1234567.89 RUB','1 234 567,89 ₽','1234567.89 руб.']:
            with self.subTest(s=s): self.assertEqual(parse_rub_amount(s)[0],'1234567.89')

    def test_missing_currency_rejected(self):
        self.assertEqual(parse_rub_amount('1200000')[0],None)

    def test_words_ambiguous_not_fabricated(self):
        x=build_normalized_card([doc('НМЦК сто тысяч рублей')])
        self.assertIsNone(x['budget_rub']['value'])
        self.assertEqual(x['budget_rub']['status'],'needs-review')
        self.assertEqual(x['money_facts'][0]['reason'],'amount_in_words_not_parsed')

    def test_correct_nmc(self):
        x=build_normalized_card([doc('НМЦК: 1 200 000,00 руб.')])
        self.assertEqual(x['budget_rub']['value'],'1200000.00')
        self.assertEqual(x['budget_rub']['status'],'extracted')

    def test_security_is_not_budget(self):
        x=build_normalized_card([doc('Обеспечение заявки: 200 000,00 рублей')])
        self.assertEqual(x['budget_rub']['status'],'not-found')
        self.assertEqual(x['money_facts'][0]['role'],'bid_security')

    def test_penalty_is_not_budget(self):
        x=build_normalized_card([doc('Штраф 200 000 рублей.')])
        self.assertEqual(x['budget_rub']['status'],'not-found')
        self.assertEqual(x['money_facts'][0]['role'],'penalty')

    def test_contract_price_not_assumed_nmc(self):
        x=build_normalized_card([doc('Цена договора 3 400 000 руб.')])
        self.assertEqual(x['budget_rub']['status'],'not-found')
        self.assertEqual(x['money_facts'][0]['role'],'contract_price')

    def test_section_number_not_price(self):
        self.assertEqual(build_normalized_card([doc('НМЦК Раздел 2.1 Требования')])['budget_rub']['status'],'not-found')

    def test_conditional_limit_is_review(self):
        x=build_normalized_card([doc('НМЦК не более 400 000 рублей')])
        self.assertEqual(x['budget_rub']['status'],'needs-review')
        self.assertIsNone(x['budget_rub']['value'])

    def test_conflicting_nmc_is_review(self):
        x=build_normalized_card([doc('НМЦК: 400 000 руб.'),doc('НМЦК: 600 000 руб.','b.pdf')])
        self.assertEqual(x['budget_rub']['status'],'needs-review')
        self.assertIsNone(x['budget_rub']['value'])

    def test_no_money_crosses_other_label(self):
        x=build_normalized_card([doc('НМЦК: не указана. Обеспечение заявки 50 000 руб.')])
        self.assertEqual(x['budget_rub']['status'],'not-found')

    def test_four_subject_phrasings(self):
        cases=[
            ('Предмет закупки: Ремонт помещений административного здания','Ремонт помещений административного здания'),
            ('Наименование объекта закупки: Поставка расходных материалов','Поставка расходных материалов'),
            ('Предмет договора: Оказание услуг уборки помещений','Оказание услуг уборки помещений'),
            ('Подрядчик обязуется выполнить капитальный ремонт водопровода','капитальный ремонт водопровода'),
        ]
        for text,expected in cases:
            with self.subTest(text=text):
                x=build_normalized_card([doc(text)])
                self.assertEqual(x['subject']['value'],expected)

    def test_subject_header_not_value(self):
        x=build_normalized_card([doc('Предмет закупки: Техническое задание. Цена договора 1 000 руб.')])
        self.assertIsNone(x['subject']['value'])

    def test_subject_stop_at_next_heading(self):
        x=build_normalized_card([doc('Предмет закупки: Ремонт входной группы Срок выполнения работ: 30 дней')])
        self.assertEqual(x['subject']['value'],'Ремонт входной группы')

    def test_section_subject_bounded_to_first_sentence(self):
        raw=('1. Объект закупки и исходные условия\n\n '
             'Ремонт крыши муниципального здания. Площадь уточняется.\n')
        text='1. Объект закупки и исходные условия Ремонт крыши муниципального здания. Площадь уточняется.'
        x=doc(text)
        x['pages'][0]['raw_text']=raw
        result=build_normalized_card([x])
        self.assertEqual(result['subject']['value'],'Ремонт крыши муниципального здания')

    def test_value_spans_real(self):
        text='НМЦК 5 555 рублей. Предмет закупки: Ремонт кровли здания'
        x=build_normalized_card([doc(text)])
        for group in ('money_facts','subject_candidates'):
            for r in x[group]:
                a,b=r['evidence']['normalized_span']
                self.assertEqual(text[a:b],r['evidence']['match'])
                self.assertIsNone(r['evidence']['bbox'])

if __name__=='__main__':unittest.main()
