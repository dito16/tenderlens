import unittest
from tender_screen.subject_price import build_normalized_card
from tender_screen.pdf_layout import derive_document_role


def cell(r,c,v):return {'row':r,'column':c,'value':v,'bbox':[c*100,r*20,(c+1)*100,(r+1)*20]}


def d(t):
    return {'file':'synthetic-table.pdf','sha256':'synthetic-hash',
            'pages':[{'page':1,'text':'','tables':[t], 'words':[]}]}


class NativeTableAndRoleTests(unittest.TestCase):
    def test_money_from_explicit_label_cell(self):
        tab={'cells':[cell(0,0,'НМЦК'),cell(0,1,'1 250 000 руб.'),
                      cell(1,0,'Обеспечение заявки'),cell(1,1,'10 000 руб.')]}
        data=build_normalized_card([d(tab)])
        self.assertEqual(data['budget_rub']['value'],'1250000.00')
        self.assertEqual({x['role'] for x in data['money_facts']},{'initial_maximum','bid_security'})

    def test_table_header_and_second_row(self):
        tab={'cells':[cell(0,0,'НМЦК'),cell(0,1,'Описание'),
                      cell(1,0,'820 000 ₽'),cell(1,1,'услуги')]}
        data=build_normalized_card([d(tab)])
        self.assertEqual(data['budget_rub']['value'],'820000.00')

    def test_table_without_currency_is_unknown(self):
        tab={'cells':[cell(0,0,'НМЦК'),cell(0,1,'120000')]}
        self.assertIsNone(build_normalized_card([d(tab)])['budget_rub']['value'])

    def test_table_subject_cell(self):
        tab={'cells':[cell(0,0,'Предмет закупки'),cell(0,1,'Ремонт основания кровли')]}
        self.assertEqual(build_normalized_card([d(tab)])['subject']['value'],'Ремонт основания кровли')

    def test_notice_title_not_filename(self):
        t='Извещение об учебной конкурентной закупке. Подача заявок начинается завтра.'
        self.assertEqual(derive_document_role([{'text':t}])['primary'],'notice')

    def test_technical_assignment_title(self):
        t='Техническое задание и дефектная ведомость. Приложение № 1.'
        self.assertEqual(derive_document_role([{'text':t}])['primary'],'technical_assignment')

    def test_contract_project_title(self):
        self.assertEqual(derive_document_role([{'text':'Проект муниципального контракта. Цена контракта 100 руб.'}])['primary'],'contract')

if __name__=='__main__':unittest.main()
