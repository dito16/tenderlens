import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import pymupdf
from tender_screen.storage import LocalStore,_csv_cell,_file_sha

EX=Path(__file__).resolve().parents[1]/'examples'/'fast_dev2_pack'

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'private'
        self.s=LocalStore(self.root);self.s.project('Demo')
    def tearDown(self):self.s.db.close();self.tmp.cleanup()
    def base(self):
        files=sorted(EX.glob('*.pdf'));return self.s.import_pdfs('Demo',files)
    def test_create_and_reopen(self):
        self.s.db.close();self.s=LocalStore(self.root)
        self.assertEqual(len(self.s.projects()),1)
    def test_duplicate_project_name(self):
        self.assertEqual(self.s.project('Demo'),self.s.project('Demo'))
    def test_empty_name_rejected(self):
        with self.assertRaises(ValueError):self.s.project(' ')
    def test_batch_three(self):self.assertEqual(self.base()['count_added'],3)
    def test_sha_dedup_idempotent(self):
        self.base();r=self.base();self.assertEqual((r['count_added'],r['count_existing']),(0,3))
    def test_distinct_storage_names(self):
        self.base()
        for d in self.s.documents('Demo'):
            self.assertTrue((self.root/d['stored_relpath']).is_file())
            self.assertEqual(_file_sha(self.root/d['stored_relpath']),d['sha256'])
    def test_explicit_revision_metadata(self):
        x=next(EX.glob('*.pdf'))
        r=self.s.import_pdfs('Demo',[x],{x.name:{'revision':'2','effective':'current','scope':'roof'}})
        row=self.s.documents('Demo')[0];self.assertEqual((row['revision'],row['scope']),('2','roof'))
    def test_symlink_rejected(self):
        target=next(EX.glob('*.pdf'));link=self.root/'test.pdf';link.symlink_to(target)
        with self.assertRaises(ValueError):self.s.import_pdfs('Demo',[link])
    def test_not_pdf_rejected(self):
        fake=self.root/'fake.pdf';fake.write_bytes(b'FAKE DATA')
        with self.assertRaises(ValueError):self.s.import_pdfs('Demo',[fake])
    def test_oversize_rejected(self):
        large=self.root/'too_big.pdf'
        with large.open('wb') as f:f.truncate(31*1024*1024)
        with self.assertRaises(ValueError):self.s.import_pdfs('Demo',[large])
    def test_batch_preflight_no_partial_writes(self):
        bad=self.root/'bad.pdf';bad.write_bytes(b'NOT PDF')
        with self.assertRaises(ValueError):self.s.import_pdfs('Demo',[next(EX.glob('*.pdf')),bad])
        self.assertEqual(len(self.s.documents('Demo')),0)
    def test_bad_metadata_rejected(self):
        f=next(EX.glob('*.pdf'))
        with self.assertRaises(ValueError):self.s.import_pdfs('Demo',[f],{f.name:{'effective':'false'}})
    def test_pdf_encrypted_rejected(self):
        # encrypted test may be platform-specific; ensure either cryptographic support or skip
        source=next(EX.glob('*.pdf'))
        with pymupdf.open(source) as d:
            out=self.root/'locked.pdf'
            d.save(out,encryption=pymupdf.PDF_ENCRYPT_AES_256,user_pw='pass',owner_pw='owner')
        with self.assertRaises(ValueError):self.s.import_pdfs('Demo',[out])
    def test_projects_isolated(self):
        self.base();self.s.project('Other')
        self.assertFalse(self.s.documents('Other'))
    def test_halfwrite_rollback_collision(self):
        pdfs=sorted(EX.glob('*.pdf'))[:2]
        # force failure on second staged file after first installed
        ordered=[]
        for p in pdfs:
            ordered.append((hashlib.sha256(p.read_bytes()).hexdigest(),p))
        bad=self.s.blobs/(ordered[1][0]+'.pdf');bad.write_bytes(b'corrupt_existing_blob')
        with self.assertRaises(ValueError):self.s.import_pdfs('Demo',pdfs)
        self.assertFalse(self.s.documents('Demo'))
        self.assertFalse((self.s.blobs/(ordered[0][0]+'.pdf')).exists())
        self.assertEqual(bad.read_bytes(),b'corrupt_existing_blob')
    def test_run_and_history(self):
        self.base();r1=self.s.analyze_project('Demo');r2=self.s.analyze_project('Demo')
        self.assertEqual(r2['run_id'],r1['run_id']+1)
        self.assertEqual(self.s.runs('Demo')[-1]['parent_run_id'],r1['run_id'])
    def test_run_creates_claims(self):
        self.base();r=self.s.analyze_project('Demo')
        self.assertGreaterEqual(len(self.s.claims(r['run_id'])),8)
    def test_raw_remains_after_review(self):
        self.base();r=self.s.analyze_project('Demo');first=self.s.claims(r['run_id'])[0]
        self.s.review_claim(first['id'],'corrected','checked PDF page 1')
        original=self.s.claims(r['run_id'])[0]
        self.assertEqual(first['machine_value_json'],original['machine_value_json'])
        self.assertEqual(first['evidence_json'],original['evidence_json'])
    def test_review_persists_restart(self):
        self.base();r=self.s.analyze_project('Demo');f=self.s.claims(r['run_id'])[0]
        self.s.review_claim(f['id'],'checked-value','verified manually');self.s.db.close();self.s=LocalStore(self.root)
        view=self.s._run_view(r['run_id'])
        self.assertEqual(view['reviewed_claims'][0]['effective_value'],'checked-value')
        self.assertEqual(view['reviewed_claims'][0]['origin'],'human_review')
    def test_multi_review_append_only(self):
        self.base();r=self.s.analyze_project('Demo');f=self.s.claims(r['run_id'])[0]
        self.s.review_claim(f['id'],'v1','note one');self.s.review_claim(f['id'],'v2','note two')
        view=self.s._run_view(r['run_id']);self.assertEqual(len(view['reviewed_claims'][0]['review_history']),2)
        self.assertEqual(view['reviewed_claims'][0]['effective_value'],'v2')
    def test_review_reject_missing_claim(self):
        with self.assertRaises(ValueError):self.s.review_claim(12345,'x','nope')
    def test_review_reject_long_comment(self):
        self.base();r=self.s.analyze_project('Demo');f=self.s.claims(r['run_id'])[0]
        with self.assertRaises(ValueError):self.s.review_claim(f['id'],'x','z'*501)
    def test_export_all_formats(self):
        self.base();r=self.s.analyze_project('Demo')
        out=self.s.export(r['run_id'],self.root/'exports')
        for f in ('analysis-v2.json','analysis-v2.html','claims-v2.csv'):self.assertTrue((out/f).exists())
        self.assertEqual(json.loads((out/'analysis-v2.json').read_text())['schema_version'],'analysis-v2')
    def test_export_versioned_no_overwrite(self):
        self.base();r=self.s.analyze_project('Demo')
        a=self.s.export(r['run_id'],self.root/'exports');b=self.s.export(r['run_id'],self.root/'exports')
        self.assertNotEqual(a,b)
    def test_csv_injection_guard(self):
        for x in ('=1+1','+SHELL','-23','@foo','  =cmd','\t=cmd'):
            self.assertTrue(_csv_cell(x).startswith("'"),x)
        self.assertEqual(_csv_cell('normal'),'normal')
    def test_html_escaped(self):
        self.base();r=self.s.analyze_project('Demo');first=self.s.claims(r['run_id'])[0]
        self.s.review_claim(first['id'],'<script>alert(1)</script>','test')
        out=self.s.export(r['run_id'],self.root/'export')
        h=(out/'analysis-v2.html').read_text()
        self.assertNotIn('<script>',h);self.assertIn('&lt;script&gt;',h)
    def test_fail_unknown_project(self):
        with self.assertRaises(ValueError):self.s.analyze_project('No project')
    def test_fail_empty_project(self):
        with self.assertRaises(ValueError):self.s.analyze_project('Demo')
    def test_valid_sqlite_foreign_keys(self):
        self.assertEqual(self.s.db.execute('PRAGMA foreign_keys').fetchone()[0],1)
    def test_history_sqlite_close_and_open(self):
        self.base();r=self.s.analyze_project('Demo')
        self.s.db.close();self.s=LocalStore(self.root)
        self.assertEqual(self.s.runs('Demo')[0]['id'],r['run_id'])
    def test_import_doesnt_mutate_source(self):
        f=next(EX.glob('*.pdf'));before=_file_sha(f)
        self.s.import_pdfs('Demo',[f]);self.assertEqual(_file_sha(f),before)
    def test_json_machine_result_kept(self):
        self.base();r=self.s.analyze_project('Demo')
        view=self.s._run_view(r['run_id']);self.assertIn('fast_dev2',view['machine_result'])
        self.assertIn('fast_dev3',view['machine_result'])
    def test_review_not_run_override(self):
        self.base();r=self.s.analyze_project('Demo');first=self.s.claims(r['run_id'])[0]
        self.s.review_claim(first['id'],'verified','user note')
        view=self.s._run_view(r['run_id'])
        self.assertNotEqual(view['reviewed_claims'][0]['machine_value'],view['reviewed_claims'][0]['effective_value'])
    def test_run_selected_latest_by_filename(self):
        self.base();r=self.s.analyze_project('Demo')
        self.assertEqual(len(r['manifest']['documents']),3)
        self.assertIn('not_official_current',self.s.runs('Demo')[0]['selection'])

    def test_question_resolution_persists_restart(self):
        demo=Path(__file__).resolve().parents[1]/'examples'/'fast_dev3_conflict_pack'
        self.s.import_pdfs('Demo',sorted(demo.glob('*.pdf')))
        r=self.s.analyze_project('Demo');qs=self.s.questions(r['run_id'])
        self.assertEqual(len(qs),3)
        self.s.resolve_question(qs[0]['local_question_id'],'Needs checked source versions')
        self.s.db.close();self.s=LocalStore(self.root)
        qs=self.s.questions(r['run_id'])
        self.assertEqual(qs[0]['status'],'resolved_by_user')
        self.assertEqual(qs[1]['status'],'unresolved')
    def test_changed_contract_new_run_diff(self):
        demo=Path(__file__).resolve().parents[1]/'examples'/'fast_dev3_conflict_pack'
        self.s.import_pdfs('Demo',sorted(demo.glob('*.pdf')))
        old=self.s.analyze_project('Demo')['run_id']
        src=demo/'03_contract.pdf';p=self.root/'revision'/'03_contract.pdf'
        p.parent.mkdir()
        with pymupdf.open(src) as document:
            document.new_page().insert_text((30,30),'New LOCAL revision used only in dev test')
            document.save(p)
        ret=self.s.import_pdfs('Demo',[p],{p.name:{'revision':'local-v2','effective':'unknown'}})
        self.assertEqual(ret['count_added'],1)
        new=self.s.analyze_project('Demo')['run_id']
        diff=self.s.compare_runs(old,new)
        self.assertEqual(len([x for x in diff['document_changes'] if x['status']=='changed']),1)
        self.assertEqual([x for x in diff['document_changes'] if x['status']=='changed'][0]['filename'],'03_contract.pdf')
        self.assertEqual(len(self.s.documents('Demo')),4)
        self.assertEqual(len(self.s._run_view(old)['machine_result']['documents']),3)
    def test_question_review_not_auto_legal_verdict(self):
        demo=Path(__file__).resolve().parents[1]/'examples'/'fast_dev3_conflict_pack'
        self.s.import_pdfs('Demo',sorted(demo.glob('*.pdf')))
        r=self.s.analyze_project('Demo');q=self.s.questions(r['run_id'])[0]
        self.s.resolve_question(q['local_question_id'],'Human reviewed the two PDFs')
        snap=self.s._run_view(r['run_id'])
        self.assertEqual(snap['review_questions'][0]['status'],'resolved_by_user')
        self.assertIsNone(snap['review_questions'][0]['legal_verdict'])
    def test_cross_project_diff_refused(self):
        self.base();a=self.s.analyze_project('Demo')['run_id']
        self.s.project('Other');self.s.import_pdfs('Other',[next(EX.glob('*.pdf'))])
        b=self.s.analyze_project('Other')['run_id']
        with self.assertRaises(ValueError):self.s.compare_runs(a,b)
    def test_unknown_run_diff_refused(self):
        self.base();a=self.s.analyze_project('Demo')['run_id']
        with self.assertRaises(ValueError):self.s.compare_runs(a,123456)
    def test_legacy_r4_output_unchanged_by_m05_storage(self):
        self.base();r=self.s.analyze_project('Demo')
        row=self.s._run_view(r['run_id'])['machine_result']
        self.assertIn('typed_fields',row)
        self.assertIn('normalized_card',row)
        self.assertIn('fast_dev2',row)

if __name__=='__main__':unittest.main()
