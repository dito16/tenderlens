from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf as fitz

from tender_screen.core import analyze, analyze_folder, evidence_from_pages, normalize, snippet

ROOT = Path(__file__).resolve().parents[1]


def document(file: str, pages: list[str]) -> dict:
    return {"file": file, "page_count": len(pages), "sha256": "synthetic-test", "pages": [
        {"page": ix + 1, "text": normalize(s), "has_text": bool(s.strip())} for ix, s in enumerate(pages)
    ]}


class RulesTest(unittest.TestCase):
    def test_whitespace_is_normalized(self):
        self.assertEqual(normalize(' A \n\t B\u00a0C '), 'A B C')

    def test_snippet_boundaries(self):
        self.assertEqual(snippet('abc', 0, 2), 'abc')

    def test_page_reference_retained(self):
        doc = document('fake.pdf', ['first', 'Аванс не предусмотрен'])
        ev = evidence_from_pages([doc], r'аванс\s+не\s+предусмотрен')
        self.assertEqual((ev[0]['file'], ev[0]['page']), ('fake.pdf', 2))

    def test_advance_conflict_detected_with_both_excerpts(self):
        r = analyze([document('notice.pdf', ['Предусмотрен аванс 20%']),
                     document('contract.pdf', ['Аванс не предусмотрен.'])])
        conflict = next(f for f in r['findings'] if f['id'] == 'advance_conflict')
        self.assertEqual({e['file'] for e in conflict['evidence']}, {'notice.pdf','contract.pdf'})
        self.assertEqual(conflict['kind'], 'risk')

    def test_advance_positive_alone_is_not_conflict(self):
        r=analyze([document('notice.pdf', ['Предусмотрен аванс 20%'])])
        self.assertNotIn('advance_conflict', [f['id'] for f in r['findings']])

    def test_advance_negative_alone_is_not_conflict(self):
        r=analyze([document('contract.pdf', ['Аванс не предусмотрен'])])
        self.assertNotIn('advance_conflict', [f['id'] for f in r['findings']])

    def test_no_auto_bid_decision(self):
        r=analyze([document('spec.pdf', ['Работы выполняются в ночное время.'])])
        self.assertIn('ЧЕЛОВЕКА',r['decision'])

    def test_unmatched_fields_are_not_claimed_absent(self):
        r=analyze([document('empty.pdf', ['Обычный текст без заданных шаблонов'])])
        self.assertTrue(all(not f['found'] for f in r['fields']))
        self.assertTrue(any('не удалось извлечь' in issue for issue in r['issues']))

    def test_scanned_pages_warn(self):
        r=analyze([document('scan.pdf', [''])])
        self.assertTrue(any('OCR' in issue for issue in r['issues']))

    def test_risk_matches_narrow_literal(self):
        r=analyze([document('contract.pdf', ['Дополнительные работы выполняются без увеличения цены договора.'])])
        self.assertIn('unpriced_changes', [f['id'] for f in r['findings']])

    def test_risk_not_inferred_from_generic_payment_keyword(self):
        r=analyze([document('contract.pdf', ['Осуществляется стандартная оплата услуг.'])])
        self.assertNotIn('deferred_payment', [f['id'] for f in r['findings']])

    def test_sample_pack_is_processed(self):
        result=analyze_folder(ROOT/'examples'/'sample_pack')
        self.assertEqual(result['stats']['files'], 3)
        self.assertEqual(result['stats']['pages'], 3)
        self.assertGreaterEqual(result['stats']['findings'], 8)
        self.assertTrue(next(f for f in result['fields'] if f['id']=='deadline')['found'])
        self.assertIn('advance_conflict', [f['id'] for f in result['findings']])

    def test_empty_folder_rejected(self):
        with TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'нет PDF'):
                analyze_folder(Path(d))

    def test_corrupted_pdf_is_reported_not_interpreted(self):
        with TemporaryDirectory() as d:
            Path(d,'bad.pdf').write_bytes(b'not a pdf')
            # Include one valid sample to ensure errors are reported alongside results.
            src=ROOT/'examples'/'sample_pack'/'01_invitation.pdf'
            Path(d,'good.pdf').write_bytes(src.read_bytes())
            r=analyze_folder(Path(d))
            self.assertEqual(r['stats']['files'],1)
            self.assertTrue(any('bad.pdf' in m for m in r['issues']))

    def test_image_only_pdf_has_ocr_warning(self):
        with TemporaryDirectory() as d:
            path=Path(d,'scan.pdf')
            pdf=fitz.open();pdf.new_page();pdf.save(path);pdf.close()
            r=analyze_folder(Path(d))
            self.assertTrue(any('OCR' in m for m in r['issues']))


if __name__ == '__main__':
    unittest.main()
