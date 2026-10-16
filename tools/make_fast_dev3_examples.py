"""Create only synthetic PDFs with named developer-known contradictions. No G4 use."""
from pathlib import Path
import argparse
import pymupdf

DOCS={
 '01_notice.pdf':[
  'Извещение о проведении закупки по ремонту кровли.',
  'Объект закупки: ремонт кровли административного корпуса.',
  'Срок подачи заявок до 23.11.2026.',
  'Членство в СРО обязательно.',
  'Аванс предусмотрен 20%.',
  'Оплата осуществляется в течение 10 рабочих дней после подписания акта.'
 ],
 '02_technical.pdf':[
  'Техническое задание по ремонту кровли.',
  'Ведомость объемов работ: ремонт кровли 125 м2.',
  'См. приложение №2 к договору.'
 ],
 '03_contract.pdf':[
  'Проект договора подряда на ремонт кровли.',
  'Членство в СРО не требуется.',
  'Аванс не предусмотрен.',
  'Оплата осуществляется в течение 20 рабочих дней после подписания акта.',
  'Гарантийный срок на работы составляет 36 месяцев.'
 ]
}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    f=next((p for p in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
        '/System/Library/Fonts/Supplemental/Arial.ttf'] if Path(p).is_file()),None)
    if not f:raise RuntimeError('No system Unicode font found; packaged examples are ready')
    for filename,lines in DOCS.items():
        doc=pymupdf.open();page=doc.new_page();page.insert_font(fontname='LocalUnicode',fontfile=f)
        for i,line in enumerate(lines):page.insert_text((36,68+30*i),line,fontname='LocalUnicode',fontsize=10)
        doc.save(a.out/filename);doc.close()
    print('GENERATED_SYNTHETIC_PDFS=3')
if __name__=='__main__':main()
