"""Resource limits are exercised against real synthetic PDFs, no held-out material."""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import pymupdf
from tender_screen.core import extract_pdf, analyze_folder
from tender_screen.processing_budget import RunGuard,ProcessingBudget,ProcessingLimitError


def pdf(path,n):
    d=pymupdf.open()
    for i in range(n):
        pg=d.new_page()
        pg.insert_text((30,70),f'Page {i+1}, synthetic-only budget check')
    d.save(path);d.close()


class Boundaries(unittest.TestCase):
    def test_page_limit(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'dev.pdf';pdf(f,4)
            with self.assertRaisesRegex(ProcessingLimitError,'pdf_page_limit_exceeded'):
                extract_pdf(f, guard=RunGuard(ProcessingBudget(max_pages_per_pdf=3)))
    def test_total_page_limit_across_pdfs(self):
        with TemporaryDirectory() as td:
            pdf(Path(td)/'a.pdf',2);pdf(Path(td)/'b.pdf',2)
            r=analyze_folder(Path(td),budget=ProcessingBudget(max_pages_total=3))
            self.assertEqual(r['processing_status'],'partial')
            self.assertEqual([x['code'] for x in r['errors']],['batch_page_limit_exceeded'])
    def test_cancelled_no_partial_file(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'cancel.pdf';pdf(f,2)
            with self.assertRaisesRegex(ProcessingLimitError,'processing_cancelled'):
                extract_pdf(f, guard=RunGuard(ProcessingBudget(),cancelled=lambda:True))
    def test_time_budget(self):
        g=RunGuard(ProcessingBudget(max_seconds=0.01))
        g.start-=1
        with self.assertRaisesRegex(ProcessingLimitError,'processing_time_budget_exceeded'):g.checkpoint()
    def test_memory_budget(self):
        g=RunGuard(ProcessingBudget(max_rss_mib=1))
        with patch.object(RunGuard,'peak_rss_mib',return_value=64):
            with self.assertRaisesRegex(ProcessingLimitError,'processing_peak_memory_budget_exceeded'):g.checkpoint()
    def test_file_byte_limit(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'bad.pdf';pdf(f,1)
            with self.assertRaisesRegex(ProcessingLimitError,'pdf_file_byte_limit_exceeded'):
                extract_pdf(f,guard=RunGuard(ProcessingBudget(max_file_bytes=200)))
    def test_text_char_limit(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'text.pdf';pdf(f,1)
            with self.assertRaisesRegex(ProcessingLimitError,'page_text_limit_exceeded'):
                extract_pdf(f,guard=RunGuard(ProcessingBudget(max_text_chars_per_page=10)))
    def test_20_page_complete(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'twenty.pdf';pdf(f,20)
            d=extract_pdf(f,guard=RunGuard(ProcessingBudget(max_pages_per_pdf=100)))
            self.assertEqual(d['page_count'],20)
    def test_100_page_complete(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'hundred.pdf';pdf(f,100)
            d=extract_pdf(f,guard=RunGuard(ProcessingBudget(max_pages_per_pdf=100)))
            self.assertEqual(d['page_count'],100)
    def test_invalid_limits(self):
        for kwargs in ({'max_seconds':0},{'max_pages_total':0},{'max_rss_mib':0}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):ProcessingBudget(**kwargs)

if __name__=='__main__':unittest.main()
