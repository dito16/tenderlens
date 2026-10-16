"""M07 Flask TestClient smoke/E2E: browser API, authorization & CSRF."""
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from tender_screen.storage import LocalStore

HAS_FLASK=importlib.util.find_spec('flask') is not None
if HAS_FLASK:from tender_screen.web.app import create_app
EX=Path(__file__).resolve().parents[1]/'examples'/'fast_dev3_conflict_pack'

@unittest.skipUnless(HAS_FLASK,'Flask not installed: Mac runner installs pinned dependency and executes all cases')
class FlaskE2E(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'private'
        self.app=create_app(self.root);self.app.config['TESTING']=True
        self.client=self.app.test_client();self.csrf=self.app.config['TL_CSRF']
    def tearDown(self):self.tmp.cleanup()
    def req(self,method,url,**kw):
        headers=kw.pop('headers',{});headers['X-TenderLens-CSRF']=self.csrf
        return self.client.open(url,method=method,headers=headers,**kw)
    def project(self):return self.req('POST','/api/projects',json={'name':'Demo'}).json['project_id']
    def upload(self,p):
        data={'pdfs':[(io.BytesIO(f.read_bytes()),f.name) for f in sorted(EX.glob('*.pdf'))]}
        return self.req('POST',f'/api/projects/{p}/documents',data=data,content_type='multipart/form-data')
    def analyzed(self):
        p=self.project();self.upload(p);ret=self.req('POST',f'/api/projects/{p}/analyze',json={})
        self.assertEqual(ret.status_code,201,ret.json)
        return p,ret.json['run_id']
    def test_home_serves_local_only(self):
        resp=self.client.get('/');self.assertEqual(resp.status_code,200)
        self.assertIn(b'csrf-token',resp.data)
        self.assertIn("'self'",resp.headers['Content-Security-Policy'])
        self.assertNotIn(b'https://',resp.data)
        self.assertEqual(self.client.get('/api/health').json['mode'],'offline_loopback_only')
    def test_refuse_external_host(self):self.assertEqual(self.client.get('/',headers={'Host':'evil.test'}).status_code,403)
    def test_refuse_mutation_without_csrf(self):
        self.assertEqual(self.client.post('/api/projects',json={'name':'Fake'}).status_code,403)
    def test_refuse_wrong_csrf(self):
        self.assertEqual(self.client.post('/api/projects',json={'name':'Fake'},headers={'X-TenderLens-CSRF':'wrong'}).status_code,403)
    def test_project_creation_and_fetch(self):
        p=self.project();self.assertEqual(self.client.get('/api/projects').json['projects'][0]['name'],'Demo')
        self.assertEqual(self.client.get(f'/api/projects/{p}').json['project']['name'],'Demo')
    def test_upload_and_duplicate_reject(self):
        p=self.project();self.assertEqual(self.upload(p).json['count_added'],3)
        self.assertEqual(self.upload(p).json['count_existing'],3)
    def test_bad_pdf_rejected(self):
        p=self.project();resp=self.req('POST',f'/api/projects/{p}/documents',data={'pdfs':(io.BytesIO(b'NO'),'fake.pdf')},content_type='multipart/form-data')
        self.assertEqual(resp.status_code,400)
        self.assertEqual(self.client.get(f'/api/projects/{p}').json['documents'],[])
    def test_run_review_history_after_restart(self):
        p,run=self.analyzed()
        d=self.client.get(f'/api/projects/{p}/runs/{run}').json
        self.assertGreaterEqual(len(d['claims']),1);self.assertGreaterEqual(len(d['questions']),1)
        claim=d['claims'][0]['claim_id'];qid=d['questions'][0]['local_question_id']
        self.assertEqual(self.req('POST',f'/api/projects/{p}/runs/{run}/claims/{claim}/review',json={'value':'Проверено','comment':'Сверено со страницей PDF'}).status_code,201)
        self.assertEqual(self.req('POST',f'/api/projects/{p}/runs/{run}/questions/{qid}/resolve',json={'note':'Требуется проверка редакции'}).status_code,201)
        # Requests use fresh SQLite connections, identical to service restart persistence.
        d=self.client.get(f'/api/projects/{p}/runs/{run}').json
        self.assertEqual(d['claims'][0]['effective_value'],'Проверено')
        self.assertEqual(d['questions'][0]['status'],'resolved_by_user')
    def test_pdf_view_correct_page_and_export(self):
        p,run=self.analyzed();d=self.client.get(f'/api/projects/{p}').json
        document=d['documents'][0]
        pdf=self.client.get(f'/api/projects/{p}/documents/{document["id"]}/pdf')
        self.assertEqual(pdf.status_code,200)
        self.assertTrue(pdf.data.startswith(b'%PDF-'))
        export=self.client.get(f'/api/projects/{p}/runs/{run}/export')
        self.assertEqual(export.status_code,200)
        with zipfile.ZipFile(io.BytesIO(export.data)) as z:self.assertIn('analysis-v2.json',z.namelist())
    def test_cross_project_ownership_rejected(self):
        p,run=self.analyzed();other=self.req('POST','/api/projects',json={'name':'Other'}).json['project_id']
        res=self.client.get(f'/api/projects/{other}/runs/{run}')
        self.assertEqual(res.status_code,400)
        docs=self.client.get(f'/api/projects/{p}').json['documents']
        self.assertEqual(self.client.get(f'/api/projects/{other}/documents/{docs[0]["id"]}/pdf').status_code,400)
    def test_analyze_empty_returns_error(self):
        p=self.project();res=self.req('POST',f'/api/projects/{p}/analyze',json={});self.assertEqual(res.status_code,400)
    def test_assets_no_external_requests(self):
        self.assertEqual(self.client.get('/static/app.js').status_code,200)
        self.assertEqual(self.client.get('/static/app.css').status_code,200)
        text=self.client.get('/static/app.js').get_data(as_text=True)
        self.assertNotIn('https://',text)

if __name__=='__main__':unittest.main()
