"""Static guardrails only; does not substitute for browser test_client E2E."""
import ast
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/'tender_screen/web'
class UIContractTests(unittest.TestCase):
    def test_flask_blueprint_compiles(self):
        ast.parse((WEB/'app.py').read_text())
    def test_no_external_resources(self):
        for p in [WEB/'templates/index.html',WEB/'static/app.js',WEB/'static/app.css']:
            content=p.read_text()
            self.assertNotIn('https://',content)
            self.assertNotIn('http://',content)
    def test_form_buttons_have_handlers(self):
        html=(WEB/'templates/index.html').read_text()
        js=(WEB/'static/app.js').read_text()
        for ident in ('create-project','upload','analyze','runs','export','close-viewer'):
            self.assertIn('id="'+ident+'"',html)
            self.assertIn("byId('"+ident+"')",js)
    def test_local_bind_only(self):
        text=(WEB/'run.py').read_text();self.assertIn("host='127.0.0.1'",text)
        self.assertNotIn("host='0.0.0.0'",text)
    def test_csrf_and_host_enforced(self):
        code=(WEB/'app.py').read_text()
        self.assertIn('compare_digest',code)
        self.assertIn('LOCAL_HOSTS',code)
        self.assertIn('X-TenderLens-CSRF',code)
    def test_evidence_link_page(self):
        script=(WEB/'static/app.js').read_text()
        self.assertIn('/pdf#page=',script)
        self.assertIn('showModal()',script)
        self.assertIn('iframe', (WEB/'templates/index.html').read_text())
    def test_all_mutations_wired(self):
        text=(WEB/'static/app.js').read_text()
        for endpoint in ('/documents','/analyze','/review','/resolve'):
            self.assertIn(endpoint,text)
        self.assertIn('method:\'POST\'',text)
    def test_no_g4_processing_hooks(self):
        for p in WEB.rglob('*.py'):
            self.assertNotIn('G4_',p.read_text())
if __name__=='__main__':unittest.main()
