"""Extra Flask E2E checks. Mark skip explicitly until Mac installs Flask."""
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
HAS_FLASK=importlib.util.find_spec('flask') is not None
if HAS_FLASK:from tender_screen.web.app import create_app

@unittest.skipUnless(HAS_FLASK, 'Requires Flask 3.1.2; Mac script must not skip')
class SecurityWeb(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=create_app(Path(self.temp.name)/'private')
        self.app.config['TESTING']=True;self.client=self.app.test_client()
        self.token=self.app.config['TL_CSRF']
    def tearDown(self):self.temp.cleanup()
    def project(self):
        return self.client.post('/api/projects',json={'name':'A'},headers={'X-TenderLens-CSRF':self.token}).json['project_id']
    def test_security_headers(self):
        resp=self.client.get('/')
        self.assertEqual(resp.status_code,200)
        self.assertIn('frame-ancestors',resp.headers['Content-Security-Policy'])
        self.assertIn('geolocation=()',resp.headers['Permissions-Policy'])
        self.assertEqual(resp.headers['Cache-Control'],'no-store')
    def test_bad_host_is_rejected(self):
        self.assertEqual(self.client.get('/api/projects',headers={'Host':'remote.example.com'}).status_code,403)
    def test_csrf_required(self):
        self.assertEqual(self.client.post('/api/projects',json={'name':'no token'}).status_code,403)
    def test_fake_pdf_blocked_while_real_project_untouched(self):
        pid=self.project()
        data={'pdfs':(io.BytesIO(b'PK\x03\x04'+b'0'*100),'fake.pdf')}
        resp=self.client.post(f'/api/projects/{pid}/documents',data=data,content_type='multipart/form-data',headers={'X-TenderLens-CSRF':self.token})
        self.assertEqual(resp.status_code,400)
        self.assertEqual(self.client.get(f'/api/projects/{pid}').json['documents'],[])
    def test_hard_size_request_rejected(self):
        resp=self.client.post('/api/projects',data=b'A'*(1024*1024+200),headers={'X-TenderLens-CSRF':self.token,'Content-Type':'application/json'})
        self.assertIn(resp.status_code,(400,413))
    def test_worker_hard_timeout_http_status(self):
        from unittest.mock import patch
        from subprocess import TimeoutExpired
        pid=self.project()
        with patch('tender_screen.web.app.subprocess.run',side_effect=TimeoutExpired('worker',125)):
            r=self.client.post(f'/api/projects/{pid}/analyze',json={},headers={'X-TenderLens-CSRF':self.token})
        self.assertEqual(r.status_code,503)
        self.assertEqual(r.json['error'],'analysis_hard_timeout_no_complete_run')

    def test_ui_has_no_external_assets(self):
        for path in ('/','/static/app.js','/static/app.css'):
            resp=self.client.get(path)
            self.assertEqual(resp.status_code,200)
            self.assertNotIn('https://',resp.get_data(as_text=True))

if __name__=='__main__':unittest.main()
