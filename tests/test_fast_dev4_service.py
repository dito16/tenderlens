"""Dependency-free M07 ownership/intake/export regression tests."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from tender_screen.web.service import (
    UIInputError, project_name, owner_run, owner_claim,owner_question,
    owner_doc_path,run_state,document_list,safe_import_streams,
    export_zip,json_review_value)
from tender_screen.storage import LocalStore

EX=Path(__file__).resolve().parents[1]/'examples'/'fast_dev3_conflict_pack'
class Uploaded:
    def __init__(self, name,raw):self.filename=name;self.stream=io.BytesIO(raw)

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.store=LocalStore(self.root/'private');self.p=self.store.project('Demo')
    def tearDown(self):self.store.db.close();self.tmp.cleanup()
    def uploads(self):return [Uploaded(f.name,f.read_bytes()) for f in sorted(EX.glob('*.pdf'))]
    def filled(self):
        self.store.import_pdfs('Demo',sorted(EX.glob('*.pdf')))
        return self.store.analyze_project('Demo')['run_id']
    def test_project_lookup(self):self.assertEqual(project_name(self.store,self.p),'Demo')
    def test_project_missing(self):
        with self.assertRaises(UIInputError):project_name(self.store,99)
    def test_import_3_pdfs_via_stream(self):
        data=safe_import_streams(self.store,self.p,self.uploads())
        self.assertEqual(data['count_added'],3)
    def test_import_dedup(self):
        safe_import_streams(self.store,self.p,self.uploads())
        self.assertEqual(safe_import_streams(self.store,self.p,self.uploads())['count_existing'],3)
    def test_import_file_name_traversal(self):
        with self.assertRaises(UIInputError):safe_import_streams(self.store,self.p,[Uploaded('../file.pdf',b'%PDF-')])
        self.assertFalse(self.store.documents('Demo'))
    def test_import_same_name(self):
        raw=next(EX.glob('*.pdf')).read_bytes()
        with self.assertRaises(UIInputError):safe_import_streams(self.store,self.p,[Uploaded('a.pdf',raw),Uploaded('a.pdf',raw)])
        self.assertFalse(self.store.documents('Demo'))
    def test_import_not_pdf_no_mutation(self):
        with self.assertRaises(ValueError):safe_import_streams(self.store,self.p,[Uploaded('fake.pdf',b'FAIL')])
        self.assertFalse(self.store.documents('Demo'))
    def test_import_max_count(self):
        with self.assertRaises(UIInputError):safe_import_streams(self.store,self.p,self.uploads()*4)
    def test_import_owner(self):
        with self.assertRaises(UIInputError):safe_import_streams(self.store,123,self.uploads())
    def test_project_documents_no_paths_exposed(self):
        self.filled()
        self.assertNotIn('stored_relpath',document_list(self.store,self.p)[0])
    def test_local_pdf_sha_validated(self):
        self.filled();docs=self.store.documents('Demo')
        path=owner_doc_path(self.store,self.p,docs[0]['id'])
        self.assertTrue(path.is_file())
        with self.assertRaises(UIInputError):owner_doc_path(self.store,987,docs[0]['id'])
    def test_corrupted_blob_rejected(self):
        self.filled();docs=self.store.documents('Demo');path=self.store.root/docs[0]['stored_relpath']
        path.write_bytes(b'garbled')
        with self.assertRaises(UIInputError):owner_doc_path(self.store,self.p,docs[0]['id'])
    def test_cross_project_run(self):
        run=self.filled();other=self.store.project('Other')
        with self.assertRaises(UIInputError):owner_run(self.store,other,run)
    def test_cross_project_claim(self):
        run=self.filled();other=self.store.project('Other')
        claim=self.store.claims(run)[0]['id']
        with self.assertRaises(UIInputError):owner_claim(self.store,other,run,claim)
    def test_cross_project_question(self):
        run=self.filled();other=self.store.project('Other')
        q=self.store.questions(run)[0]['local_question_id']
        with self.assertRaises(UIInputError):owner_question(self.store,other,run,q)
    def test_run_details_and_export_zip(self):
        run=self.filled();data=run_state(self.store,self.p,run)
        self.assertGreaterEqual(len(data['questions']),3)
        buf=export_zip(self.store,self.p,run)
        with zipfile.ZipFile(buf) as z:
            self.assertEqual(set(z.namelist()),{'analysis-v2.json','claims-v2.csv','analysis-v2.html'})
            self.assertIn('reviewed_claims',json.loads(z.read('analysis-v2.json')))
    def test_json_review_safe(self):
        self.assertEqual(json_review_value('10'),10)
        self.assertEqual(json_review_value('осмотрено'),'осмотрено')
        with self.assertRaises(UIInputError):json_review_value('{"a":1}')
    def test_cross_project_export(self):
        run=self.filled();other=self.store.project('Other')
        with self.assertRaises(UIInputError):export_zip(self.store,other,run)
    def test_no_gold_holdout_touched(self):
        self.filled()
        self.assertFalse(list(self.root.rglob('*holdout*')))

if __name__=='__main__':unittest.main()
