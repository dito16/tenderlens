from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from tender_screen.__main__ import main
from tender_screen.core import analyze_folder
from tender_screen.report import render_html, write_csv

ROOT=Path(__file__).resolve().parents[1]


class RenderTest(unittest.TestCase):
    def test_html_escaping_of_source_quote_and_filename(self):
        r={"decision":"safe", "disclaimer":"demo", "stats":{"files":1,"pages":1,"findings":1,"risks":1},
           "documents":[{"file":"<script>.pdf","page_count":1,"sha256":"x"}],
           "fields":[{"title":"<img>","found":False,"evidence":[]}],"issues":["<bad>"],
           "findings":[{"id":"x","kind":"risk","title":"<h1>","explanation":"a & b",
                        "next_action":"<stop>","evidence":[{"file":"<script>.pdf","page":1,
                                                              "quote":"<script>alert(1)</script>","match":"x"}]}]}
        html=render_html(r)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',html)
        self.assertIn('&lt;img&gt;',html)
        self.assertNotIn('<script>',html)
        self.assertIn('a &amp; b',html)

    def test_csv_has_bom_for_excel(self):
        r=analyze_folder(ROOT/'examples'/'sample_pack')
        with TemporaryDirectory() as d:
            p=Path(d)/'out.csv';write_csv(r,p)
            self.assertTrue(p.read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertIn('advance_conflict',p.read_text(encoding='utf-8-sig'))

    def test_cli_generates_all_three_reports(self):
        with TemporaryDirectory() as d:
            code=main(['run','--input-dir',str(ROOT/'examples'/'sample_pack'),'--out-dir',d])
            self.assertEqual(code,0)
            for n in ('report.html','analysis.json','evidence.csv'):
                self.assertGreater((Path(d)/n).stat().st_size,100)
            result=json.loads((Path(d)/'analysis.json').read_text(encoding='utf-8'))
            self.assertEqual(result['stats']['files'],3)

    def test_cli_missing_folder_fails(self):
        with TemporaryDirectory() as d:
            self.assertEqual(main(['run','--input-dir',str(Path(d)/'missing'),'--out-dir',d]),2)


if __name__ == '__main__':
    unittest.main()
