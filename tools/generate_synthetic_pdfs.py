"""OPTIONAL development tool. Generate invented RFQ documents. Requires reportlab.

No research PDF, company data, or customer document is copied here.
"""
from pathlib import Path
import os
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


def font_path(env_name: str, candidates: list[str]) -> str:
    options = ([os.environ[env_name]] if env_name in os.environ else []) + candidates
    for candidate in options:
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError(f"No suitable Cyrillic font found; set {env_name} to an installed TTF file")


FONT = font_path('TENDERLENS_FONT_FILE', [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
    '/System/Library/Fonts/Supplemental/Arial.ttf',
])
FONT_BOLD = font_path('TENDERLENS_FONT_BOLD_FILE', [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
    FONT,
])


def make(path: Path, title: str, parts: list[tuple[str,str]]):
    pdfmetrics.registerFont(TTFont('DejaVu', FONT))
    pdfmetrics.registerFont(TTFont('DejaVuBold', FONT_BOLD))
    normal=ParagraphStyle('CustomNormal',fontName='DejaVu',fontSize=10.5,leading=17,spaceAfter=12)
    head=ParagraphStyle('CustomHead',fontName='DejaVuBold',fontSize=18,leading=25,spaceAfter=24,textColor=colors.HexColor('#1A4855'))
    sub=ParagraphStyle('CustomSub',fontName='DejaVuBold',fontSize=11,leading=16,spaceBefore=10,spaceAfter=8)
    label=ParagraphStyle('CustomLabel',fontName='DejaVu',fontSize=8,leading=13,textColor=colors.HexColor('#526A75'))
    items=[Paragraph(title,head),Paragraph('ВЫМЫШЛЕННЫЙ ПРИМЕР · НЕ ЯВЛЯЕТСЯ РЕАЛЬНОЙ ЗАКУПКОЙ',label),Spacer(1,25)]
    for header,paragraph in parts:
        items.extend([Paragraph(header,sub),Paragraph(paragraph,normal)])
    doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=55,leftMargin=55,topMargin=62,bottomMargin=55,title=title,author='TenderLens synthetic demo')
    doc.build(items)


if __name__=='__main__':
    out=Path(__file__).resolve().parents[1]/'examples'/'sample_pack'
    out.mkdir(parents=True, exist_ok=True)
    make(out/'01_invitation.pdf','Приглашение к участию',[
        ('Процедура','Запрос коммерческих предложений на косметический ремонт офисных помещений. Организатор: ООО «Городские пространства» (вымышленная организация). Предмет закупки: отделочные работы в офисе, Москва.'),
        ('Сроки и бюджет','Прием заявок до 15.11.2026. Бюджет закупки 8 400 000 руб. Срок выполнения работ 60 календарных дней.'),
        ('Оплата','Предусмотрен аванс 20% от цены договора. Остальные условия устанавливаются в проекте договора.'),
        ('Допуск','Обязательный осмотр объекта 05.11.2026. Для допуска требуется подтверждение членства в СРО, если соответствующее требование применимо к предмету работ.'),
    ])
    make(out/'02_technical_assignment.pdf','Техническое задание',[
        ('Описание объекта','Предмет работ: штукатурка и окраска стен, частичная замена напольных покрытий, демонтаж локальных конструкций.'),
        ('Объёмы','Ведомость объёмов работ является предварительной. Объёмы уточняются после осмотра объекта и обмеров.'),
        ('Условия выполнения','Работы выполняются в действующем здании в ночное время. На объекте действует пропускной режим.'),
        ('Приёмка','Исполнитель должен вести исполнительную документацию и передавать документы на приёмку по согласованному графику.'),
    ])
    make(out/'03_draft_contract.pdf','Проект договора подряда',[
        ('Цена и расчёты','Аванс не предусмотрен. Оплата производится в течение 45 календарных дней после подписания актов КС-2 и КС-3.'),
        ('Изменение работ','Заказчик вправе требовать дополнительные работы без увеличения цены договора. Порядок согласования изменений требует уточнения.'),
        ('Удержание','Удержание 5% от суммы выполненных работ предусмотрено до окончания гарантийного срока.'),
        ('Приёмка','Приёмка по актам КС-2 и КС-3 сопровождается проверкой исполнительной документации.'),
    ])
    print('SYNTHETIC_DOCUMENTS=3')
