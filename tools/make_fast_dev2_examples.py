"""Generate three synthetic PDF input files for FAST DEV 2 CLI demonstration."""
from pathlib import Path
import argparse
import pymupdf

CONTENTS={
  '01_notice.pdf':['Извещение о проведении закупки',
    'Наименование объекта закупки: ремонт кровли административного здания.',
    'НМЦК: 6 750 000,00 руб.',
    'Срок подачи заявок до 23.11.2026 в 15:30.',
    'Аванс не предусмотрен.'],
  '02_technical.pdf':['Техническое задание. Ведомость объемов работ:',
    'Ведомость объемов работ: ремонт кровли 125 м2.',
    'Срок выполнения работ 45 календарных дней.',
    'Срок подготовки схемы 4 рабочих дня.',
    'Осмотр объекта обязателен.'],
  '03_contract.pdf':['Проект договора подряда',
    'Оплата осуществляется в течение 10 рабочих дней после подписания акта.',
    'Гарантийный срок на работы составляет 36 месяцев.',
    'Гарантийный срок на материалы составляет 12 месяцев.',
    'Членство в СРО не требуется.'],
}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    for name,lines in CONTENTS.items():
        doc=pymupdf.open();page=doc.new_page()
        # DejaVu Sans supports Cyrillic. Use system font only when available,
        # fallback: PDF built-in extraction tests still run on synthetic Latin.
        fontpath='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
        mac_candidates=['/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
                        '/System/Library/Fonts/Supplemental/Arial.ttf']
        f=next((q for q in [fontpath]+mac_candidates if Path(q).exists()),None)
        if f:page.insert_font(fontname='LCL',fontfile=f);name_font='LCL'
        else:raise RuntimeError('No local Cyrillic font available; use bundled examples/realistic_packs instead')
        for i,line in enumerate(lines):
            page.insert_text((35,65+i*30),line,fontname=name_font,fontsize=10)
        doc.save(a.out/name);doc.close()
    print('SYNTHETIC_INPUTS=3')
if __name__=='__main__':main()
