"""M02 PDF layout extractor: native words/blocks and two independent table heuristics.

No OCR or hidden fallback. Geometry is only emitted when PyMuPDF provides it.
"""
from __future__ import annotations
import re
import unicodedata
from dataclasses import asdict

from .document_model import LayoutWord, TextBlock, TableCell, LayoutTable


def _bbox(box):
    if box is None:
        return None
    try:
        nums = tuple(round(float(x), 2) for x in box)
        if len(nums) == 4 and nums[0] <= nums[2] and nums[1] <= nums[3]:
            return nums
    except (TypeError, ValueError):
        pass
    return None


def _norm(s):
    return re.sub(r'\s+', ' ', s.replace('\u00ad', '')).strip()


def _mapped_span(text, token, cursor):
    """Only claim a span when word text matches exactly (case preserved)."""
    token = _norm(token)
    if not token:
        return None, cursor
    where = text.find(token, cursor)
    if where < 0:
        return None, cursor
    return (where, where + len(token)), where + len(token)


def _detect_tables(page):
    find_tables = getattr(page, 'find_tables', None)
    if not callable(find_tables):
        return [], ['table_extractor_unavailable']
    warnings = []
    # 'lines' relies on vector rulings; 'text' uses aligned text columns.
    # Text-derived tables remain candidates, not authoritative cell boundaries.
    for strategy in ('lines', 'text'):
        try:
            collection = find_tables(strategy=strategy)
        except Exception as exc:
            warnings.append('table_' + strategy + '_failed:' + type(exc).__name__)
            continue
        extracted = []
        for tab in list(getattr(collection, 'tables', []))[:30]:
            try:
                values = tab.extract() or []
                rows = len(values)
                cols = max((len(x or []) for x in values), default=0)
                if rows < 2 or cols < 2 or rows > 1000 or cols > 80:
                    continue
                # Reject fabricated tables from single-column paragraph alignment.
                meaningful = sum(bool(str(v or '').strip()) for row in values for v in (row or []))
                if meaningful < 3 or meaningful < rows:
                    continue
                raw_boxes = list(getattr(tab, 'cells', []) or [])
                cells = []
                for r, row in enumerate(values):
                    for c in range(cols):
                        val = (row[c] if row and c < len(row) else '') or ''
                        idx = r * cols + c
                        b = _bbox(raw_boxes[idx]) if idx < len(raw_boxes) else None
                        cells.append(TableCell(r, c, str(val).strip(), b, r == 0))
                extracted.append(asdict(LayoutTable(strategy,
                    'structural_candidate' if strategy == 'lines' else 'text_alignment_candidate',
                    _bbox(getattr(tab, 'bbox', None)), rows, cols, tuple(cells))))
            except (AttributeError, TypeError, ValueError, IndexError):
                warnings.append('table_candidate_rejected')
        if extracted:
            return extracted, warnings
    return [], warnings


def _role(text):
    """Role comes from multiple body/header signals, never the filename.

    A substantive title match near the start is stronger than a generic
    appendix mention or a disclaimer about another document role.
    """
    t = _norm(text).lower()[:16000]
    anchors = {
        'technical_assignment': (
            (r'\bтехническое задание\b', 4),
            (r'\bтребовани[яе]\s+к\s+(?:товару|работам|услугам)\b', 2)),
        'notice': (
            (r'\bизвещение\s+о(?:б)?\s+[^.]{0,36}?закупке\b', 4),
            (r'\bизвещение\s+о\s+проведении\b', 4),
            (r'\bподач[аи]\s+заявок\b', 1)),
        'contract': (
            (r'\bпроект\s+(?:[а-я]+\s+){0,2}(?:договора|контракта)\b', 4),
            (r'\bдоговор\s+подряда\b', 4),
            (r'\b(?:заказчик|подрядчик|исполнитель)\s+обязуется\b', 2),
            (r'\bцена\s+контракта\b', 1)),
        'bill_of_quantities': (
            (r'\b(?:дефектная\s+ведомость|ведомость\s+об[ъь]?[её]мов\s+работ)\b', 3),
            (r'\b(?:единица\s+измерения|количество)\b', 1)),
        'appendix': (
            (r'\bприложение\s*(?:№|номер)?\s*\d+\b', 1),
            (r'\bк\s+договору\b', 1)),
    }
    scores = {}
    for role, patterns in anchors.items():
        val=0
        for pat, weight in patterns:
            for m in list(re.finditer(pat, t, re.I))[:3]:
                preceding=t[max(0,m.start()-22):m.start()]
                if re.search(r'не\s+является\s*$',preceding): continue
                val += weight if m.start() < 650 else max(1,weight//3)
        if val: scores[role]=val
    accepted = sorted(((k,v) for k,v in scores.items() if v >= 2),key=lambda kv:(-kv[1],kv[0]))
    best = accepted[0][0] if accepted and (len(accepted)==1 or accepted[0][1]>accepted[1][1]) else 'unknown'
    if best=='unknown' and len(accepted)>1 and accepted[0][1]==accepted[1][1]:
        # A combined title "Technical assignment and bill of quantities" is
        # classified by its leading named role, while both remain candidates.
        top = [(m.start(),role) for role,pat in (
            ('technical_assignment',r'\bтехническое задание\b'),
            ('bill_of_quantities',r'\b(?:дефектная ведомость|ведомость об[ъь]?[её]мов работ)\b'))
            for m in list(re.finditer(pat,t[:650]))[:1]]
        if len(top)==2 and accepted[0][0] in dict(top).values() and accepted[1][0] in dict(top).values():
            best=min(top)[1]
    return {'primary': best,'candidates':[{'role':k,'score':v,'basis':'body_title_and_clause_anchors'}
           for k,v in accepted], 'basis':'body_text_only_not_filename', 'review_required':best=='unknown'}


SECTION_RE = re.compile(r'(?im)(?:^|\n)\s*(?:\d+[.)]\s*)?(?P<title>предмет\s+(?:договора|закупки)|'
                        r'начальн\w*\s+максимальн\w*\s+цена|'
                        r'техническое\s+задание|условия\s+оплаты|'
                        r'сроки?\s+(?:поставки|выполнения)|обеспечение\s+заявки)\s*[:.]?')


def layout_for_page(page, raw_text: str, normalized_text: str, page_number: int):
    raw_blocks = page.get_text('blocks', sort=True)
    blocks = []
    for i, block in enumerate(raw_blocks):
        if len(block) < 7: continue
        b = _bbox(block[:4]); typ = block[6]
        if b is None: continue
        blocks.append(asdict(TextBlock(str(block[4]) if typ == 0 else '',b,
                'text' if typ == 0 else 'image', i)))
    cursor = 0
    words = []
    for w in page.get_text('words', sort=True):
        box = _bbox(w[:4])
        if box is None: continue
        span, cursor = _mapped_span(normalized_text, str(w[4]), cursor)
        words.append(asdict(LayoutWord(str(w[4]), box, int(w[5]), int(w[6]), int(w[7]), span)))
    tables, warnings = _detect_tables(page)
    has_images = any(block['kind'] == 'image' for block in blocks) or bool(page.get_images(full=False))
    has_text = bool(normalized_text)
    if has_text:
        content_status = 'mixed_text_and_images' if has_images else 'searchable'
    else:
        content_status = 'image_only_ocr_required' if has_images else 'empty_or_vector_only'
        warnings.append('no_searchable_text_no_ocr_performed')
    rotation = int(page.rotation)
    if rotation: warnings.append('page_rotation_' + str(rotation))
    sections = [{'title':m.group('title'), 'raw_span':[m.start('title'), m.end('title')],
                 'basis':'line_heading'} for m in SECTION_RE.finditer(raw_text)]
    return {
        'rotation':rotation, 'width_pt':round(page.rect.width, 2), 'height_pt':round(page.rect.height, 2),
        'blocks':blocks, 'words':words, 'tables':tables,
        'content_status':content_status, 'warnings': warnings,
        'section_anchors': sections,
        'layout_source':'pymupdf_pdf_points',
        'word_span_coverage':sum(x['normalized_span'] is not None for x in words),
        'word_count':len(words),
    }


def derive_document_role(pages):
    # The first pages carry most title/structure evidence. No filename evidence.
    text=' '.join((p.get('text') or '')[:9000] for p in pages[:3])
    return _role(text)


def span_bbox(page: dict, start: int, end: int):
    """Union only when word spans fully cover the evidence's non-space characters.

    This is conservative; if words can't prove coverage, no bbox is returned.
    """
    if start >= end: return None
    relevant = [w for w in page.get('words', []) if w.get('normalized_span')
                and w['normalized_span'][0] < end and w['normalized_span'][1] > start]
    if not relevant: return None
    coverage = [False] * (end-start)
    for w in relevant:
        a,b=w['normalized_span']
        for i in range(max(start,a), min(end,b)):
            coverage[i-start] = True
    txt=page.get('text','')[start:end]
    if len(txt)!=len(coverage) or not all(c or txt[i].isspace() for i,c in enumerate(coverage)):
        return None
    boxes=[w['bbox'] for w in relevant]
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]
