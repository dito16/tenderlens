"""M04 independent error/export contract tests with generated input documents."""
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import hashlib
import json
import unittest

import pymupdf as fitz

from tender_screen.__main__ import main
from tender_screen.core import analyze_folder, normalize
from tender_screen.report import _spreadsheet_text, write_csv, render_html


def make_pdf(path: Path, text: str):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((45, 80), text, fontname='helv', fontsize=11)
    doc.save(path)
    doc.close()


class M04ContractTests(unittest.TestCase):
    def test_complete_metadata(self):
        with TemporaryDirectory() as root:
            d = Path(root)
            make_pdf(d / 'normal.pdf', 'Budget 2500000 RUB')
            r = analyze_folder(d)
            self.assertEqual((r['schema_version'], r['processing_status']), ('1.0.0', 'complete'))
            self.assertEqual(r['errors'], [])
            self.assertEqual(r['input_files_total'], 1)

    def test_partial_corrupt_and_two_good(self):
        with TemporaryDirectory() as root:
            input_dir = Path(root) / 'input'; input_dir.mkdir()
            output_dir = Path(root) / 'output'
            make_pdf(input_dir / 'good1.pdf', 'First')
            make_pdf(input_dir / 'good2.pdf', 'Second')
            (input_dir / 'bad.pdf').write_bytes(b'not a valid PDF')
            self.assertEqual(main(['run','--input-dir',str(input_dir),'--out-dir',str(output_dir)]), 3)
            result = json.loads((output_dir / 'analysis.json').read_text())
            self.assertEqual(result['processing_status'], 'partial')
            self.assertEqual(result['stats']['files'], 2)
            self.assertEqual(result['input_files_total'], 3)
            self.assertEqual(result['errors'][0]['file'], 'bad.pdf')
            self.assertEqual(result['errors'][0]['code'], 'pdf_parse_error')
            self.assertIn('partial',(output_dir / 'report.html').read_text())
            with (output_dir / 'evidence.csv').open(encoding='utf-8-sig', newline='') as f:
                self.assertGreaterEqual(len(list(csv.reader(f, delimiter=';'))), 1)

    def test_all_corrupt_failed_and_no_invented_fields(self):
        with TemporaryDirectory() as root:
            inp = Path(root) / 'input'; inp.mkdir()
            out = Path(root) / 'output'
            (inp / 'wrong.pdf').write_bytes(b'bad')
            self.assertEqual(main(['run','--input-dir',str(inp),'--out-dir',str(out)]), 2)
            r = json.loads((out / 'analysis.json').read_text())
            self.assertEqual(r['processing_status'], 'failed')
            self.assertEqual(r['stats']['files'], 0)
            self.assertTrue(r['errors'])
            self.assertTrue(all(f['status']=='ambiguous' and f['value'] is None
                                for f in r['typed_fields'].values()))

    def test_missing_folder_remains_error_2(self):
        with TemporaryDirectory() as root:
            self.assertEqual(main(['run','--input-dir',str(Path(root)/'absent'),
                                   '--out-dir',str(Path(root)/'out')]), 2)

    def test_registry_round_trip_and_no_orphan_evidence(self):
        from tender_screen.core import analyze_folder
        sample = Path(__file__).resolve().parents[1]/'examples'/'sample_pack'
        r=analyze_folder(sample)
        ids={ev['id'] for ev in r['evidence']}
        self.assertEqual(len(ids),len(r['evidence']))
        self.assertGreater(len(ids),10)
        for f in r['findings']:
            self.assertTrue(set(f['evidence_ids']).issubset(ids))
        for condition in r['conditions']:
            self.assertIn(condition['evidence_id'], ids)
        for conflict in r['conflicts']:
            self.assertTrue(set(conflict['evidence_ids']).issubset(ids))
        for field in r['typed_fields'].values():
            self.assertTrue(set(field['evidence_ids']).issubset(ids))
        documents={d['file']:d['sha256'] for d in r['documents']}
        for ev in r['evidence']:
            source=sample/ev['file']
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), ev['source_sha256'])
            self.assertEqual(documents[ev['file']],ev['source_sha256'])
            with fitz.open(source) as pdf:
                txt=normalize(pdf[ev['page']-1].get_text('text',sort=True))
            if ev.get('normalized_span'):
                a,b=ev['normalized_span'];self.assertEqual(txt[a:b],ev['match'])
            self.assertTrue(ev['references'])

    def test_export_references_exactly_registry(self):
        sample=Path(__file__).resolve().parents[1]/'examples'/'sample_pack'
        r=analyze_folder(sample)
        with TemporaryDirectory() as root:
            csvfile=Path(root)/'evidence.csv';write_csv(r,csvfile)
            with csvfile.open(encoding='utf-8-sig',newline='') as f:
                rows=list(csv.DictReader(f,delimiter=';'))
            self.assertEqual({x['Evidence ID'] for x in rows}, {e['id'] for e in r['evidence']})
            html=render_html(r)
            for conflict in r['conflicts']:
                for ident in conflict['evidence_ids']:
                    self.assertIn(ident,html)
            for field in r['typed_fields'].values():
                for ident in field['evidence_ids']:
                    self.assertIn(ident,html)

    def test_csv_formula_defense_and_quote_breakout(self):
        attack='=SUM(1;2)";=1+1\r\n@cmd'
        ev={'id':'EV-safe','file':'+file.pdf','page':1,'source_sha256':'a'*64,
            'quote':attack, 'match':'@cmd','normalized_span':[0,4],
            'references':['finding:test']}
        r={'evidence':[ev], 'processing_status':'complete'}
        with TemporaryDirectory() as root:
            p=Path(root)/'a.csv';write_csv(r,p)
            with p.open(encoding='utf-8-sig',newline='') as f:
                rows=list(csv.reader(f,delimiter=';'))
            self.assertEqual(len(rows),2)
            self.assertEqual(len(rows[0]),len(rows[1]))
            self.assertTrue(rows[1][2].startswith('\t+'))
            self.assertTrue(rows[1][5].startswith('\t='))
            self.assertNotIn('\n',rows[1][5])
            self.assertNotIn('\r',rows[1][5])
            self.assertEqual(ev['quote'],attack) # raw JSON remains unchanged

    def test_formula_prefix_variants(self):
        for value in ('=1+1', '+2', '-2', '@abc', '  =2', '\t=3', '＝A'):
            with self.subTest(value=value):
                self.assertTrue(_spreadsheet_text(value).startswith('\t'))
        self.assertEqual(_spreadsheet_text('normal value'),'normal value')

    def test_html_escapes_malicious_error_and_quote(self):
        r={'decision':'ok','disclaimer':'demo','stats':{'files':0,'pages':0,'findings':0,'risks':0},
           'fields':[],'findings':[],'documents':[], 'issues':[],
           'processing_status':'partial','schema_version':'1.0.0',
           'errors':[{'file':'<script>alert(1)</script>.pdf','code':'pdf_parse_error'}],
           'typed_fields':{},'conflicts':[]}
        html=render_html(r)
        self.assertNotIn('<script>',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('partial',html)

    def test_two_runs_byte_identical(self):
        sample=Path(__file__).resolve().parents[1]/'examples'/'sample_pack'
        with TemporaryDirectory() as root:
            out1=Path(root)/'first';out2=Path(root)/'second'
            self.assertEqual(main(['run','--input-dir',str(sample),'--out-dir',str(out1)]),0)
            self.assertEqual(main(['run','--input-dir',str(sample),'--out-dir',str(out2)]),0)
            for name in ('analysis.json','evidence.csv','report.html'):
                self.assertEqual((out1/name).read_bytes(),(out2/name).read_bytes())

    def test_symlinked_pdf_not_enumerated(self):
        with TemporaryDirectory() as root:
            d=Path(root);src=d/'actual.pdf';make_pdf(src,'Safe')
            (d/'linked.pdf').symlink_to(src)
            r=analyze_folder(d)
            self.assertEqual(r['input_files_total'],1)
            self.assertEqual(r['processing_status'],'complete')

    def test_error_output_contains_no_absolute_path(self):
        with TemporaryDirectory() as root:
            inp=Path(root)/'input';inp.mkdir()
            (inp/'bad.pdf').write_bytes(b'X')
            r=analyze_folder(inp)
            self.assertNotIn(root,json.dumps(r['errors']))


if __name__=='__main__': unittest.main()
