"""FAST DEV 5 adversarial IO, zero external URLs, evidence correctness, migrations."""
from __future__ import annotations
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from tender_screen.security import validate_local_pdf, is_private_data_root, check_static_offline
from tender_screen.storage import LocalStore, _csv_cell
from tender_screen.domain_pipeline import build_domain_pipeline
from tender_screen.document_model import *

ROOT=Path(__file__).resolve().parents[1]
EX=ROOT/'examples'/'fast_dev3_conflict_pack'

class AdversarialIO(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory()
        self.dir=Path(self.work.name)
    def tearDown(self):self.work.cleanup()

    def test_refuse_renamed_zip(self):
        p=self.dir/'payload.pdf'
        with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('evil.txt','A'*50000)
        with self.assertRaisesRegex(ValueError,'pdf_header_required'):validate_local_pdf(p)
    def test_refuse_html_as_pdf(self):
        p=self.dir/'evil.pdf';p.write_bytes(b'<script>fetch("https://evil.com")</script>')
        with self.assertRaisesRegex(ValueError,'pdf_header_required'):validate_local_pdf(p)
    def test_refuse_false_extension(self):
        p=self.dir/'evil.txt';p.write_bytes(b'%PDF-1.5\n')
        with self.assertRaises(ValueError):validate_local_pdf(p)
    def test_refuse_pdf_symlink(self):
        origin=EX/'01_notice.pdf'; link=self.dir/'evil.pdf';link.symlink_to(origin)
        with self.assertRaisesRegex(ValueError,'invalid_pdf_path'):validate_local_pdf(link)
    def test_refuse_private_db_symlink(self):
        self.dir.joinpath('tenderlens.sqlite3').symlink_to(self.dir/'target')
        with self.assertRaisesRegex(ValueError,'symlink_private_store_entry'):is_private_data_root(self.dir)
    def test_refuse_private_blobs_symlink(self):
        self.dir.joinpath('pdf_blobs').symlink_to(self.dir/'target')
        with self.assertRaisesRegex(ValueError,'symlink_private_store_entry'):is_private_data_root(self.dir)
    def test_accept_synthetic_pdf(self):self.assertTrue(validate_local_pdf(EX/'01_notice.pdf'))
    def test_no_browser_remote_assets(self):
        self.assertTrue(check_static_offline(ROOT/'tender_screen'/'web'/'static'))
    def test_offline_audit_blocks_tracker(self):
        d=self.dir/'assets';d.mkdir();(d/'demo.js').write_text('fetch("https://tracker.example/collect")')
        with self.assertRaisesRegex(ValueError,'external_browser_url'):check_static_offline(d)
    def test_csv_formula_escaped(self):
        for s in ('=1+1','+1','-1','@SUM(A:A)','  =HYPERLINK("evil")','\t=1+1'):
            self.assertEqual(_csv_cell(s)[0],"'")
    def test_csv_normal_not_escaped(self):self.assertEqual(_csv_cell('125 м2'),'125 м2')
    def test_import_atomic_bad_batch(self):
        p=self.dir/'spoof.pdf';p.write_bytes(b'%PDF'+b'bad')
        with LocalStore(self.dir/'private') as db:
            db.project('A')
            with self.assertRaises(ValueError):db.import_pdfs('A',[EX/'01_notice.pdf',p])
            self.assertEqual(db.documents('A'),[])
    def test_sqlite_no_symlink_data_root(self):
        src=self.dir/'real';src.mkdir();alias=self.dir/'alias';alias.symlink_to(src)
        with self.assertRaises(ValueError):LocalStore(alias)
    def test_separate_run_revision_and_persistence(self):
        root=self.dir/'private'
        with LocalStore(root) as store:
            store.project('Demo')
            ing=store.import_pdfs('Demo',sorted(EX.glob('*.pdf')))
            self.assertEqual(ing['count_added'],3)
            run=store.analyze_project('Demo')
            self.assertEqual(run['review_questions'],3)
            state=store._run_view(run['run_id'])
            self.assertEqual(len(state['review_questions']),3)
            advances=[f for f in state['reviewed_claims'] if f['kind']=='advance']
            self.assertEqual(len(advances),2)
            self.assertEqual(set(f['machine_value'] for f in advances),{'explicit_positive','explicit_negative'})
            cid=advances[0]['claim_id']
            store.review_claim(cid,'explicit_positive','Ручная проверка исходного файла')
        with LocalStore(root) as store:
            a=store._run_view(run['run_id'])
            r=next(x for x in a['reviewed_claims'] if x['claim_id']==cid)
            self.assertEqual(r['origin'],'human_review')
            self.assertEqual(len(r['review_history']),1)
            self.assertEqual(store.db.execute('select max(version) from schema_migrations').fetchone()[0],1)
    def test_html_export_escapes_review_injection(self):
        root=self.dir/'htmlprivate'
        with LocalStore(root) as store:
            store.project('Demo')
            store.import_pdfs('Demo',sorted(EX.glob('*.pdf')))
            run=store.analyze_project('Demo')
            first=store._run_view(run['run_id'])['reviewed_claims'][0]
            store.review_claim(first['claim_id'],'<script>alert(1)</script>','HTML safety smoke')
            directory=store.export(run['run_id'],self.dir/'export')
        html=(directory/'analysis-v2.html').read_text()
        self.assertNotIn('<script>alert(1)</script>',html)
        self.assertIn('&lt;script&gt;',html)

    def test_zip_archive_never_uploads(self):
        renamed=self.dir/'zip.pdf'
        with zipfile.ZipFile(renamed,'w') as z:
            z.writestr('../escape.txt','attack')
        with LocalStore(self.dir/'private') as store:
            store.project('A')
            with self.assertRaisesRegex(ValueError,'pdf_header_required'):
                store.import_pdfs('A',[renamed])
            self.assertEqual(store.documents('A'),[])

    def test_reproducible_cli_machine_json(self):
        from tender_screen.core import analyze_folder
        # Low level deterministic regression: same physical input, no gold/holdout.
        a=analyze_folder(EX)
        b=analyze_folder(EX)
        self.assertEqual(json.dumps(a,sort_keys=True,ensure_ascii=False,default=str),json.dumps(b,sort_keys=True,ensure_ascii=False,default=str))
    def test_worker_isolated_subprocess(self):
        root=self.dir/'private'
        with LocalStore(root) as db:
            pid=db.project('Demo');db.import_pdfs('Demo',sorted(EX.glob('*.pdf')))
        ret=subprocess.run([sys.executable,'-m','tender_screen.web.worker','--data-root',str(root),
                         '--project-id',str(pid)],capture_output=True,text=True,cwd=ROOT,timeout=45)
        self.assertEqual(ret.returncode,0,ret.stderr)
        responses=[line.split('TENDERLENS_WORKER_JSON:',1)[1] for line in ret.stdout.splitlines() if line.startswith('TENDERLENS_WORKER_JSON:')]
        self.assertEqual(len(responses),1,ret.stdout[:300])
        payload=json.loads(responses[0])
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['result']['review_questions'],3)
    def test_ui_renders_evidence_not_raw_json(self):
        js=(ROOT/'tender_screen'/'web'/'static'/'app.js').read_text()
        self.assertIn('evidence-comparison',js)
        self.assertIn('evidenceCard(e)',js)
        self.assertNotIn('Технические данные (при необходимости)',js)  # FAST DEV 7: demo copy removed
        self.assertNotIn('JSON.stringify(payload,null,2)',js)
        self.assertIn('Аванс предусмотрен',js)
    def test_new_boundary_guards(self):
        src=(ROOT/'tender_screen'/'web'/'app.py').read_text()
        self.assertIn('subprocess.run',src)
        self.assertIn('WEB_ANALYZE_HARD_TIMEOUT_SECONDS',src)
        self.assertIn('Permissions-Policy',src)
        self.assertIn('Cross-Origin-Opener-Policy',src)
        self.assertIn('compare_digest',src)
        self.assertIn('localhost',src)
        self.assertNotIn("host='0.0.0.0'",src)
    def test_no_urllib_requests_in_web_code(self):
        web=ROOT/'tender_screen'/'web'
        for name in ('app.py','service.py','run.py','worker.py'):
            code=(web/name).read_text()
            self.assertNotIn('requests.get(',code)
            self.assertNotIn('urllib.request.urlopen(',code)

if __name__=='__main__':unittest.main()
