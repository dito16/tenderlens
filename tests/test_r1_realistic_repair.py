"""Independent oracles for realistic-audit R1 repair.

The PDFs are fictional training examples authored separately from the parser.
This suite checks semantic behavior, not only matching sample output snapshots.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf as fitz

from tender_screen.context import sentence
from tender_screen.core import analyze, analyze_folder
from tender_screen.fields import extract_typed_fields
from tender_screen.report import render_html, write_csv

ROOT = Path(__file__).resolve().parent / 'realistic_packs'


def doc(filename: str, content: str):
    return {'file': filename, 'sha256': hashlib.sha256((filename + content).encode()).hexdigest(),
            'page_count': 1, 'pages': [{'page': 1, 'text': content,
                                       'raw_text': content, 'has_text': bool(content)}]}


class R1ClauseTests(unittest.TestCase):
    def test_01_dotted_date_not_boundary(self):
        text = 'Ранее действовавшая редакция от 01.09.2026 содержала текст «Аванс 10% предусмотрен»; не применяется.'
        start = text.index('Аванс')
        self.assertIn('Ранее действовавшая редакция', sentence(text, start, start + 5)[0])

    def test_02_decimal_point_not_boundary(self):
        text = 'В прежней редакции аванс 12.5% предусмотрен. Сейчас аванс не предусмотрен.'
        start = text.index('аванс')
        self.assertIn('В прежней редакции', sentence(text, start, start + 5)[0])

    def test_03_extended_negative_retention_not_a_positive(self):
        phrase = 'Удержание 5% от цены контракта в качестве гарантийного резерва не предусмотрено.'
        result = analyze([doc('contract.pdf', phrase)])
        self.assertFalse([f for f in result['findings'] if f['id'] == 'retention'])
        self.assertEqual(result['typed_fields']['retention_percent']['status'], 'ambiguous')
        self.assertIsNone(result['typed_fields']['retention_percent']['value'])
        self.assertEqual(result['typed_fields']['retention_percent']['candidates'][0]['reason'], 'possible_negated_clause')
        self.assertTrue([c for c in result['conditions'] if c['family'] == 'retention_terms'
                         and c['polarity'] == 'explicit_negative'])

    def test_04_positive_retention_still_extracted(self):
        r = analyze([doc('contract.pdf', 'Гарантийное удержание 5% предусмотрено на период устранения замечаний.')])
        self.assertEqual(r['typed_fields']['retention_percent']['value'], '5')
        self.assertTrue([f for f in r['findings'] if f['id'] == 'retention'])

    def test_05_conditional_retention_is_not_extracted(self):
        r = analyze([doc('contract.pdf', 'Удержание 5% может потребоваться, если условия изменятся.')])
        self.assertNotEqual(r['typed_fields']['retention_percent']['status'], 'extracted')

    def test_06_hist_quotation_with_date_not_live_advance(self):
        historical = ('Ранее действовавшая редакция от 01.09.2026 содержала текст '
                      '«Аванс 10% предусмотрен»; данная формулировка приведена только как '
                      'исторический пример и не подлежит применению.')
        current = 'Аванс не предусмотрен. Оплата только после приёмки.'
        r = analyze([doc('spec.pdf', historical), doc('contract.pdf', current)])
        self.assertFalse(r['conflicts'])
        self.assertFalse([f for f in r['findings'] if f['id'] == 'advance_conflict'])
        candidates = r['typed_fields']['advance_percent']['candidates']
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['validity'], 'historical')
        self.assertIsNone(r['typed_fields']['advance_percent']['value'])

    def test_07_current_advance_not_displaced_by_hist_quote(self):
        r = analyze([doc('spec.pdf',
                         'Ранее действовавшая редакция от 01.09.2026: Аванс 10% предусмотрен. '
                         'Аванс 20% предусмотрен.')])
        # A new independently punctuated sentence is current; the older one
        # remains evidence but does not become an active competing value.
        self.assertEqual(r['typed_fields']['advance_percent']['value'], '20')
        self.assertEqual({c['validity'] for c in r['typed_fields']['advance_percent']['candidates']},
                         {'historical', 'parsed'})

    def test_08_real_current_advance_conflict_still_flagged(self):
        r = analyze([doc('notice.pdf', 'Аванс 20% предусмотрен.'),
                     doc('contract.pdf', 'Аванс не предусмотрен.')])
        self.assertEqual([c['family'] for c in r['conflicts']], ['advance_terms'])

    def test_09_sro_scope_tension_is_not_claimed_as_legal_conflict(self):
        r = analyze([doc('notice.pdf', 'Членство в СРО требуется для кровельных работ.'),
                     doc('spec.pdf', 'СРО не требуется для отдельных работ в ведомости.')])
        self.assertEqual([c['family'] for c in r['conflicts']], ['sro_scope'])
        conflict = r['conflicts'][0]
        self.assertEqual(conflict['status'], 'needs-review')
        self.assertTrue(conflict['human_review_required'])
        self.assertIn('scope', conflict['reason'])
        self.assertEqual({e['file'] for e in conflict['evidence']}, {'notice.pdf', 'spec.pdf'})

    def test_10_sro_same_file_not_cross_document(self):
        r = analyze([doc('single.pdf', 'Членство в СРО требуется. СРО не требуется для иной категории работ.')])
        self.assertNotIn('sro_scope', [c['family'] for c in r['conflicts']])

    def test_11_duration_with_incompatible_units_requires_review(self):
        r = analyze([doc('notice.pdf', 'Срок выполнения работ 30 рабочих дней.'),
                     doc('contract.pdf', 'Срок выполнения работ 40 календарных дней.')])
        c = r['conflicts'][0]
        self.assertEqual(c['family'], 'duration_terms')
        self.assertTrue(c['human_review_required'])
        self.assertEqual({(x['value'], x['unit']) for x in c['declared_values']},
                         {('30','work_days'),('40','calendar_days')})

    def test_12_matching_duration_not_reported_as_conflict(self):
        r = analyze([doc('a.pdf', 'Срок выполнения работ 30 рабочих дней.'),
                     doc('b.pdf', 'Срок выполнения работ 30 рабочих дней.')])
        self.assertFalse(r['conflicts'])
        self.assertEqual(r['typed_fields']['duration']['value'], '30')

    def test_13_duration_variants_same_pdf_not_cross_document(self):
        r = analyze([doc('one.pdf', 'Срок выполнения работ 30 рабочих дней. Срок выполнения работ 40 календарных дней.')])
        self.assertNotIn('duration_terms', [c['family'] for c in r['conflicts']])
        self.assertEqual(r['typed_fields']['duration']['status'], 'ambiguous')

    def test_14_headline_fields_use_typed_budget(self):
        r = analyze([doc('a.pdf', 'Цена контракта 5 820 000 руб. Аванс не предусмотрен.')])
        budget = next(f for f in r['fields'] if f['id'] == 'budget')
        self.assertEqual((budget['found'], budget['value']), (True, '5820000'))
        self.assertIn('5820000', render_html(r))
        payment = next(f for f in r['fields'] if f['id'] == 'payment')
        self.assertTrue(payment['found'])

    def test_15_tz_heading_does_not_fake_scope(self):
        r = analyze([doc('a.pdf', 'Техническое задание. Другой текст без объекта.')])
        self.assertFalse(next(f for f in r['fields'] if f['id'] == 'scope')['found'])

    def test_16_real_description_can_be_scope(self):
        r = analyze([doc('a.pdf', 'Объект закупки: текущий ремонт помещений здания и лестницы.')])
        self.assertTrue(next(f for f in r['fields'] if f['id'] == 'scope')['found'])


class R1RealisticPDFTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.consistent = analyze_folder(ROOT / '01_CONSISTENT_TENDER')
        cls.conflicting = analyze_folder(ROOT / '02_CONFLICTING_TENDER')

    def test_17_consistent_no_conflict_and_no_fake_retention(self):
        r = self.consistent
        self.assertEqual((r['stats']['files'], r['stats']['pages'], r['processing_status']),
                         (3,6,'complete'))
        self.assertFalse(r['conflicts'])
        self.assertFalse([f for f in r['findings'] if f['id']=='retention'])
        self.assertNotEqual(r['typed_fields']['retention_percent']['status'], 'extracted')
        self.assertEqual(r['typed_fields']['budget_rub']['value'], '5820000')
        self.assertEqual(next(f for f in r['fields'] if f['id']=='budget')['value'], '5820000')
        self.assertEqual(r['typed_fields']['duration']['unit'], 'calendar_days')

    def test_18_conflicting_three_scoped_reviews(self):
        r = self.conflicting
        self.assertEqual((r['stats']['files'], r['stats']['pages'], r['processing_status']),
                         (3,5,'complete'))
        self.assertEqual({c['family'] for c in r['conflicts']},
                         {'advance_terms','sro_scope','duration_terms'})
        self.assertTrue(all(c['human_review_required'] for c in r['conflicts']))
        self.assertEqual(r['typed_fields']['budget_rub']['value'], '6750000')
        self.assertEqual(r['typed_fields']['duration']['status'], 'ambiguous')
        self.assertEqual(r['typed_fields']['advance_percent']['status'], 'ambiguous')
        candidates = r['typed_fields']['advance_percent']['candidates']
        self.assertTrue(any(c['validity']=='historical' and c['value']=='10' for c in candidates))

    def test_19_real_pdfs_without_notice_no_false_advance(self):
        base=ROOT / '02_CONFLICTING_TENDER'
        names=('02_tekhnicheskoe_zadanie.pdf','03_proekt_kontrakta.pdf')
        from tender_screen.core import extract_pdf
        r=analyze([extract_pdf(base/name) for name in names])
        self.assertNotIn('advance_terms', {c['family'] for c in r['conflicts']})
        self.assertFalse([f for f in r['findings'] if f['id']=='advance_conflict'])

    def test_20_every_conflict_evidence_verifiable_in_pdf(self):
        base=ROOT / '02_CONFLICTING_TENDER'
        seen={}
        for conflict in self.conflicting['conflicts']:
            self.assertEqual(len(conflict['evidence_ids']),2)
            for entry in conflict['evidence']:
                file=base/entry['file']
                self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),entry['source_sha256'])
                with fitz.open(file) as source:
                    self.assertGreaterEqual(entry['page'],1)
                    self.assertLessEqual(entry['page'],len(source))
                    from tender_screen.core import normalize
                    text=normalize(source[entry['page']-1].get_text('text',sort=True))
                    a,b=entry['normalized_span']
                    self.assertEqual(text[a:b],entry['match'])
                seen[entry['id']]=entry
        self.assertEqual(len(seen),6)

    def test_21_safe_exports_and_stable_determinism(self):
        r=analyze_folder(ROOT/'02_CONFLICTING_TENDER')
        with TemporaryDirectory() as tmp:
            csv=Path(tmp)/'evidence.csv'
            write_csv(r,csv)
            self.assertTrue(csv.read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertEqual(len({ev['id'] for ev in r['evidence']}),len(r['evidence']))
            self.assertNotIn('<script>',render_html(r))
            self.assertTrue(all(eid in {ev['id'] for ev in r['evidence']}
                                for c in r['conflicts'] for eid in c['evidence_ids']))
        with TemporaryDirectory() as tmp:
            a=analyze_folder(ROOT/'02_CONFLICTING_TENDER')
            self.assertEqual(json.dumps(r,ensure_ascii=False,sort_keys=True),
                             json.dumps(a,ensure_ascii=False,sort_keys=True))


if __name__ == '__main__':
    unittest.main()
