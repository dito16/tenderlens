"""M02 independent, synthetic golden semantics tests (no external tender files)."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf as fitz

from tender_screen.core import analyze, analyze_folder
from tender_screen.fields import SCHEMA_VERSION, extract_typed_fields


def document(text, name='synthetic.pdf', has_text=True):
    return {'file': name, 'sha256': hashlib.sha256((name + text).encode()).hexdigest(),
            'page_count': 1,
            'pages': [{'page': 1, 'text': text, 'raw_text': text, 'has_text': has_text}]}


def field(text, key, name='synthetic.pdf'):
    return extract_typed_fields([document(text, name)])[key]


class TypedFieldGoldenTests(unittest.TestCase):
    def test_date_dd_mm_yyyy_and_provenance(self):
        d = field('Прием заявок до 14.11.2026.', 'deadline')
        self.assertEqual((d['status'], d['value'], d['unit']), ('extracted', '2026-11-14', 'date'))
        self.assertEqual(d['evidence'][0]['page'], 1)
        self.assertEqual(len(d['evidence'][0]['source_sha256']), 64)
        self.assertIn('14.11.2026', d['evidence'][0]['quote'])
        self.assertEqual(d['evidence_ids'], [d['evidence'][0]['id']])

    def test_invalid_calendar_date_is_ambiguous_null(self):
        d = field('Прием заявок до 31.02.2026.', 'deadline')
        self.assertEqual((d['status'], d['value']), ('ambiguous', None))
        self.assertEqual(d['candidates'][0]['validity'], 'invalid')

    def test_ambiguous_two_different_dates(self):
        r=extract_typed_fields([document('Прием заявок до 14.11.2026.','a.pdf'),
                                document('Прием заявок до 15.11.2026.','b.pdf')])['deadline']
        self.assertEqual((r['status'], r['value']), ('ambiguous', None))
        self.assertEqual(len(r['evidence_ids']), 2)

    def test_days_explicit_working(self):
        d=field('Срок выполнения работ 30 рабочих дней', 'duration')
        self.assertEqual((d['status'],d['value'],d['unit']), ('extracted','30','work_days'))

    def test_unspecified_days_no_unit_inference(self):
        d=field('Срок выполнения работ 30 дней', 'duration')
        self.assertEqual((d['status'],d['value']), ('ambiguous',None))
        self.assertEqual(d['candidates'][0]['reason'], 'day_type_not_specified')

    def test_calendar_days_and_months_distinct(self):
        self.assertEqual(field('Срок выполнения работ 60 календарных дней','duration')['unit'],'calendar_days')
        self.assertEqual(field('Срок выполнения работ 3 месяца','duration')['unit'],'months')

    def test_rub_amount_whitespace_decimal_comma(self):
        d=field('Бюджет закупки 2\u00a0500\u00a0000,50 руб.', 'budget_rub')
        self.assertEqual((d['status'],d['value'],d['unit']),('extracted','2500000.50','RUB'))

    def test_missing_currency_not_extracted(self):
        d=field('Цена договора 2 500 000', 'budget_rub')
        self.assertEqual((d['status'],d['value']),('ambiguous',None))
        self.assertEqual(d['candidates'][0]['reason'],'currency_not_explicit')

    def test_missing_budget_not_zero(self):
        d=field('Бюджет отсутствует.','budget_rub')
        self.assertEqual((d['status'],d['value']),('not-found',None))

    def test_decimal_percent_and_0_percent(self):
        a=field('Аванс 12,5%','advance_percent')
        b=field('Аванс 0%','advance_percent')
        self.assertEqual((a['status'],a['value'] ),('extracted','12.5'))
        self.assertEqual((b['status'],b['value'] ),('extracted','0'))

    def test_percent_beyond_100_fails_closed(self):
        d=field('Аванс 150%','advance_percent')
        self.assertEqual((d['status'],d['value']),('ambiguous',None))
        self.assertEqual(d['candidates'][0]['reason'],'percent_out_of_range')

    def test_negative_retention_never_extracted_positive(self):
        d=field('Удержание 5% не предусмотрено','retention_percent')
        self.assertEqual((d['status'],d['value']),('ambiguous',None))
        self.assertEqual(d['candidates'][0]['reason'],'possible_negated_clause')

    def test_advance_disagreement_not_silently_extracted(self):
        docs=[document('Предусмотрен аванс 20%','invitation.pdf'),
              document('Аванс не предусмотрен','contract.pdf')]
        d=extract_typed_fields(docs)['advance_percent']
        self.assertEqual((d['status'],d['value']),('ambiguous',None))
        self.assertEqual(d['confidence_basis'],'opposing_advance_wording_requires_review')
        self.assertEqual(len(d['evidence_ids']),1)

    def test_blank_pdf_requires_ocr_not_invented_value(self):
        doc=document('',has_text=False)
        d=extract_typed_fields([doc])['deadline']
        self.assertEqual((d['status'],d['value']),('ocr-required',None))

    def test_same_input_deterministic_evidence_ids(self):
        docs=[document('Аванс 20% Бюджет закупки 2 500 000 руб.')]
        self.assertEqual(json.dumps(extract_typed_fields(docs),sort_keys=True),
                         json.dumps(extract_typed_fields(docs),sort_keys=True))

    def test_real_generated_cyrillic_pdf_via_pymupdf(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'new-synthetic.pdf'
            pdf=fitz.open();page=pdf.new_page()
            page.insert_htmlbox(fitz.Rect(25,25,550,450),
                '<p>Прием заявок до 14.11.2026. Бюджет закупки 2 500 000 руб. '
                'Срок выполнения работ 30 рабочих дней. Удержание 5%.</p>')
            pdf.save(p);pdf.close()
            r=analyze_folder(Path(d))
            self.assertEqual((r['stats']['files'],r['stats']['pages']),(1,1))
            self.assertEqual(r['schema_version'],SCHEMA_VERSION)
            fields=r['typed_fields']
            self.assertEqual(fields['deadline']['value'],'2026-11-14')
            self.assertEqual(fields['budget_rub']['value'],'2500000')
            self.assertEqual(fields['duration']['unit'],'work_days')
            self.assertEqual(fields['retention_percent']['value'],'5')
            self.assertEqual(fields['budget_rub']['evidence'][0]['source_sha256'],
                             hashlib.sha256(p.read_bytes()).hexdigest())

    def test_real_default_sample_conflict_fails_closed(self):
        samples=Path(__file__).resolve().parents[1]/'examples'/'sample_pack'
        r=analyze_folder(samples)
        self.assertEqual(r['schema_version'],'1.0.0')
        self.assertEqual(r['typed_fields']['advance_percent']['status'],'ambiguous')
        self.assertIsNone(r['typed_fields']['advance_percent']['value'])
        self.assertEqual(r['typed_fields']['budget_rub']['value'],'8400000')
        self.assertEqual(r['typed_fields']['deadline']['value'],'2026-11-15')


if __name__=='__main__':
    unittest.main()
