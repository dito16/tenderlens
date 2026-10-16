"""FAST DEV 7: explicit UI-only regression, shared by both isolated trees."""
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/'tender_screen/web'

class CleanDemoUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(WEB/'templates/index.html').read_text(encoding='utf-8')
        cls.js=(WEB/'static/app.js').read_text(encoding='utf-8')
        cls.css=(WEB/'static/app.css').read_text(encoding='utf-8')
    def test_logo_is_local_svg_asset(self):
        self.assertIn('tenderlens-logo.svg',self.html)
        self.assertIn('alt="Логотип TenderLens"',self.html)
        self.assertNotIn('class="logo">TL</span>',self.html)
        self.assertTrue((WEB/'static/tenderlens-logo.svg').is_file())
        root=ET.parse(WEB/'static/tenderlens-logo.svg').getroot()
        self.assertTrue(root.tag.endswith('svg'))
        forbidden={'script','foreignObject','image','iframe'}
        for node in root.iter():
            self.assertNotIn(node.tag.rsplit('}',1)[-1],forbidden)
            for attr,value in node.attrib.items():
                self.assertFalse(attr.startswith('on'))
                self.assertNotIn('javascript:',value.lower())
                self.assertNotIn('http://',value.lower())
                self.assertNotIn('https://',value.lower())
    def test_service_elements_preserved(self):
        for ident in ('status','projects','create-project','pdfs','upload','analyze','runs','export','claims-panel','questions-panel','history-panel','viewer','pdf-frame','close-viewer'):
            self.assertIn('id="'+ident+'"',self.html)
        self.assertIn('csrf-token',self.html)
    def test_demo_copy_no_internal_prose(self):
        for phrase in ('Local research workspace','ВЕРСИЯ ДЛЯ РАЗРАБОТКИ','Нет CDN','bbox может быть недоступна','Не юридическое заключение','ред.: unknown','Технические данные (при необходимости)'):
            self.assertNotIn(phrase,self.html+self.js)
    def test_readable_comparison_and_units(self):
        for term in ('compareValue(fk,e,q.kind)','рабочих дней','Аванс предусмотрен','СРО требуется','Срок подачи заявок','Объём работ'):
            self.assertIn(term,self.js)
        self.assertNotIn('report.textContent=JSON.stringify(result,null,2)',self.js)
    def test_no_external_assets(self):
        for text in (self.html,self.js,self.css):
            self.assertNotIn('https://',text)
            self.assertNotIn('http://',text)

if __name__=='__main__':unittest.main()
