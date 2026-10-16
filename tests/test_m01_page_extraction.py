"""M01 independent synthetic checks for page extraction and traceable spans.

No third-party documents, no OCR, no network access. Generated PDFs are local,
used only during the tests and removed with TemporaryDirectory.
"""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf as fitz

from tender_screen.core import (
    analyze_folder, evidence_from_pages, extract_pdf,
    normalize, normalize_with_offsets,
)


def make_pdf(path: Path, pages: list[str]) -> None:
    pdf = fitz.open()
    for content in pages:
        page = pdf.new_page()
        if content:
            # Built-in PDF font deliberately uses ASCII for portable tests.
            page.insert_text((50, 72), content, fontsize=11)
    pdf.save(path)
    pdf.close()


class M01PageExtractionTests(unittest.TestCase):
    def test_normalization_preserves_existing_output(self):
        cases = [" A \n\t B\u00a0C ", "ab\u00adcd", " \u00a0\n ", "\nHello  world\t", ""]
        for raw in cases:
            with self.subTest(raw=repr(raw)):
                normalized, spans = normalize_with_offsets(raw)
                self.assertEqual(normalized, normalize(raw))
                self.assertEqual(len(spans), len(normalized))

    def test_raw_offsets_survive_soft_hyphen_and_whitespace(self):
        raw = "\n Advance\u00ad\t  20% \n"
        normalized, ranges = normalize_with_offsets(raw)
        self.assertEqual(normalized, "Advance 20%")
        self.assertEqual(normalize(raw[ranges[0][0]:ranges[-1][1]]), normalized)
        page = {"page": 2, "text": normalized, "raw_text": raw, "has_text": True}
        document = {"file": "fake.pdf", "sha256": "synthetic-test", "pages": [page]}
        item = evidence_from_pages([document], r"Advance\s+20%")[0]
        self.assertEqual(item["normalized_span"], [0, len(normalized)])
        self.assertEqual(item["span_status"], "verified")
        self.assertEqual(item["span_basis"], "normalized_page_text")
        a, b = item["raw_span"]
        self.assertEqual(normalize(raw[a:b]), item["match"])

    def test_short_text_page_is_searchable_without_ocr_warning(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "short.pdf"
            make_pdf(path, ["Short text"])
            document = extract_pdf(path)
            page = document["pages"][0]
            self.assertEqual(page["text"], "Short text")
            self.assertTrue(page["has_text"])
            self.assertEqual(page["text_status"], "searchable")
            report = analyze_folder(Path(td))
            self.assertFalse(any("short.pdf" in issue and "OCR" in issue for issue in report["issues"]))

    def test_empty_page_produces_no_fabricated_extracted_text(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "blank.pdf"
            make_pdf(path, [""])
            document = extract_pdf(path)
            page = document["pages"][0]
            self.assertEqual(page["raw_text"], "")
            self.assertEqual(page["normalized_text"], "")
            self.assertEqual(page["text_status"], "no_searchable_text")
            self.assertFalse(page["has_text"])
            self.assertTrue(any("OCR" in issue for issue in analyze_folder(Path(td))["issues"]))

    def test_two_pages_and_source_sha_page_match(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "two-pages.pdf"
            make_pdf(path, ["No relevant token", "Payment 30 days"])
            doc = extract_pdf(path)
            self.assertEqual(doc["page_count"], 2)
            self.assertEqual(doc["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            item = evidence_from_pages([doc], r"Payment\s+30\s+days")[0]
            self.assertEqual(item["page"], 2)
            self.assertEqual(item["source_sha256"], doc["sha256"])
            self.assertEqual(item["span_status"], "verified")
            self.assertIn("Payment 30 days", item["quote"])

    def test_multiline_search_preserves_page_trace(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "multiline.pdf"
            make_pdf(path, ["Advance\n20 percent"])
            doc = extract_pdf(path)
            self.assertIn("Advance 20 percent", doc["pages"][0]["text"])
            item = evidence_from_pages([doc], r"Advance\s+20\s+percent")[0]
            self.assertEqual(item["match"], "Advance 20 percent")
            self.assertEqual(item["span_status"], "verified")
            a, b = item["raw_span"]
            self.assertEqual(normalize(doc["pages"][0]["raw_text"][a:b]), item["match"])

    def test_legacy_documents_do_not_claim_raw_offsets(self):
        doc = {"file": "fake.pdf", "sha256": "fixture-only", "pages": [
            {"page": 1, "text": "Advance 20%", "has_text": True}]}
        ev = evidence_from_pages([doc], r"Advance\s+20%")[0]
        self.assertEqual(ev["normalized_span"], [0, 11])
        self.assertEqual(ev["span_status"], "unavailable")
        self.assertNotIn("raw_span", ev)


if __name__ == "__main__":
    unittest.main()
