"""FAST DEV M02 tests: twelve+ positive and negative structural cases."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import pymupdf as fitz
from tender_screen.core import extract_pdf, analyze_folder
from tender_screen.pdf_layout import span_bbox, derive_document_role


def make_pdf(path, modes=('text',)):
    d=fitz.open()
    for mode in modes:
        p=d.new_page(width=550,height=780)
        if mode=='text': p.insert_text((36,70),'Technical assignment\nRequirements to works',fontsize=12)
        if mode=='image':
            # PDF with actual raster image and no machine-readable text
            pic=fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,20,20),0)
            pic.clear_with(200)
            p.insert_image(fitz.Rect(100,100,160,160),pixmap=pic)
        if mode=='table':
            cols=[40,210,400];rows=[60,92,125,158]
            for x in cols:p.draw_line((x,rows[0]),(x,rows[-1]))
            for y in rows:p.draw_line((cols[0],y),(cols[-1],y))
            for (x,y,text) in [(50,80,'Header'),(220,80,'Value'),(50,112,'Budget'),(220,112,'120000'),(50,145,'Delivery'),(220,145,'yes')]:
                p.insert_text((x,y),text,fontsize=10)
        if mode=='rotated':
            p.insert_text((40,50),'rotated text');p.set_rotation(90)
    d.save(path);d.close()


class LayoutTests(unittest.TestCase):
    def test_sha_pages(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'a.pdf';make_pdf(f,('text','image'))
            d=extract_pdf(f)
            self.assertEqual(d['page_count'],2)
            self.assertEqual(d['sha256'],hashlib.sha256(f.read_bytes()).hexdigest())

    def test_text_geometry(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'text.pdf';make_pdf(f)
            p=extract_pdf(f)['pages'][0]
            self.assertTrue(p['words']);self.assertTrue(p['blocks'])
            self.assertEqual(p['content_status'],'searchable')
            self.assertTrue(all(len(w['bbox'])==4 for w in p['words']))

    def test_word_span_aligned(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'text.pdf';make_pdf(f)
            p=extract_pdf(f)['pages'][0]
            self.assertGreater(p['word_span_coverage'],0)
            word=next(w for w in p['words'] if w['normalized_span'])
            a,b=word['normalized_span'];self.assertEqual(p['text'][a:b],word['text'])

    def test_coordinates_when_supported(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'text.pdf';make_pdf(f)
            p=extract_pdf(f)['pages'][0]
            word=next(w for w in p['words'] if w['normalized_span'])
            self.assertIsNotNone(span_bbox(p,*word['normalized_span']))

    def test_do_not_invent_bbox(self):
        self.assertIsNone(span_bbox({'text':'yes','words':[]},0,3))

    def test_partial_word_mapping_no_bbox(self):
        p={'text':'Hello UNKNOWN', 'words':[{'normalized_span':[0,5], 'bbox':[1,2,3,4]}]}
        self.assertIsNone(span_bbox(p,0,len(p['text'])))

    def test_image_only_ocr_required(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'raster.pdf';make_pdf(f,('image',))
            p=extract_pdf(f)['pages'][0]
            self.assertFalse(p['has_text']);self.assertEqual(p['text'],'')
            self.assertEqual(p['content_status'],'image_only_ocr_required')

    def test_empty_page(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'empty.pdf';make_pdf(f,('empty',))
            p=extract_pdf(f)['pages'][0]
            self.assertFalse(p['has_text']);self.assertEqual(p['content_status'],'empty_or_vector_only')

    def test_mixed_partial_pages(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'mixed.pdf';make_pdf(f,('text','image'))
            d=extract_pdf(f)
            self.assertTrue(d['pages'][0]['has_text']);self.assertFalse(d['pages'][1]['has_text'])
            self.assertNotEqual(d['pages'][0]['text_status'],d['pages'][1]['text_status'])

    def test_rotation(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'rot.pdf';make_pdf(f,('rotated',))
            p=extract_pdf(f)['pages'][0]
            self.assertEqual(p['rotation'],90)
            self.assertIn('page_rotation_90',p['warnings'])

    def test_vector_table_cells_and_headers(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'table.pdf';make_pdf(f,('table',))
            tables=extract_pdf(f)['pages'][0]['tables']
            self.assertTrue(tables, 'native table was not found')
            t=tables[0];self.assertEqual(t['column_count'],2)
            self.assertTrue(any(c['value']=='Header' and c['is_header'] for c in t['cells']))
            self.assertTrue(any(c['value']=='120000' and not c['is_header'] for c in t['cells']))

    def test_role_unknown_not_from_filename(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'project_contract_notice.pdf';make_pdf(f,('text',))
            self.assertEqual(extract_pdf(f)['document_role']['primary'],'unknown')

    def test_role_cannot_assume_from_word(self):
        pages=[{'text':'См. документация и договор в приложении.'}]
        self.assertEqual(derive_document_role(pages)['primary'],'unknown')

    def test_section_anchors_in_raw_text(self):
        with TemporaryDirectory() as td:
            f=Path(td)/'a.pdf';make_pdf(f,('text',))
            p=extract_pdf(f)['pages'][0]
            self.assertIsInstance(p['section_anchors'],list)

    def test_broken_pdf_partial(self):
        with TemporaryDirectory() as td:
            base=Path(td);make_pdf(base/'ok.pdf')
            (base/'broken.pdf').write_bytes(b'bad pdf content')
            result=analyze_folder(base)
            self.assertTrue(result['errors'])
            self.assertEqual(result['processing_status'],'partial')

    def test_50_pdf_limit(self):
        with TemporaryDirectory() as td:
            d=Path(td); (d/'x.pdf').write_bytes(b'not read')
            for i in range(51): (d/f'{i}.pdf').write_bytes(b'x')
            with self.assertRaisesRegex(ValueError,'50 PDF'):
                analyze_folder(d)

    def test_30m_limit(self):
        with TemporaryDirectory() as td:
            d=Path(td);(d/'too_big.pdf').write_bytes(b'x'*(30*1024*1024+1))
            res=analyze_folder(d)
            self.assertIn('file_too_large',[x['code'] for x in res['errors']])

if __name__=='__main__':unittest.main()
