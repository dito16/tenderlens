"""Conservative typed candidates with shared sentence-level context.

No automatic legal decisions or contract-revision priority. Quotations of old
clauses never become active values. Decimal values remain strings.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import re

from .context import classify, sentence, advance_conditions

SCHEMA_VERSION = '1.0.0'

DATE = re.compile(
    r'\b(?:при[её]м|подач[аиу]|крайний\s+срок)\s+(?:заявок|предложений)'
    r'[^.!?]{0,65}?\b(?:до|по)\s*(?P<value>\d{1,2}\.\d{1,2}\.\d{4})(?!\d)', re.I)
DURATION = re.compile(
    r'\bсрок\s+(?:выполнения|проведения)\s+работ\b[^.!?]{0,70}?'
    r'\b(?P<value>\d{1,4})\s*(?P<unit>рабочих|календарных)?\s*'
    r'(?P<kind>дн(?:ей|я|ь)|месяц(?:ев|а|ы)?)\b', re.I)
AMOUNT_TOKEN = r'(?P<value>(?:\d{1,3}(?:[\s\u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?|\d{4,12}(?:[.,]\d{1,2})?|\d{1,3}(?:[.,]\d{1,2})?))'
AMOUNT = re.compile(
    r'\b(?:бюджет\s+закупки|цена\s+договора|цена\s+контракта|сумма\s+договора|'
    r'стоимость\s+работ|начальн\w*\s+(?:максимальн\w*\s+)?цена)\b'
    r'(?P<prefix>[^.!?\d]{0,35})' + AMOUNT_TOKEN +
    r'(?P<currency>\s*(?:руб(?:лей|ля|\.)?|₽|RUB))?', re.I)
ADVANCE = re.compile(
    r'\b(?:предусмотрен\s+аванс|аванс(?:овый\s+плат[её]ж)?)\b'
    r'[^.!?]{0,36}?(?P<value>\d{1,3}(?:[.,]\d{1,2})?)\s*%', re.I)
RETENTION = re.compile(
    r'\bудержани[ея]\b[^.!?]{0,30}?(?P<value>\d{1,3}(?:[.,]\d{1,2})?)\s*%', re.I)

SPECS = (
    ('deadline', 'date', DATE),
    ('duration', 'duration', DURATION),
    ('advance_percent', 'percent', ADVANCE),
    ('retention_percent', 'percent', RETENTION),
    ('budget_rub', 'RUB', AMOUNT),
)

_NO_ADVANCE_CLAUSE = re.compile(r'\b(?:аванс\s+не\s+предусмотрен|аванс\s+отсутствует|без\s+аванса)\b', re.I)
_NEG_AFTER = re.compile(r'\bне\s+(?:предусмотрен\w*|выплачива\w*|производ\w*|применя\w*)\b', re.I)
_CONDITIONAL = re.compile(r'\b(?:не\s+более|не\s+менее|примерно|ориентировочно|около|до|от)\b', re.I)


def _decimal(raw: str) -> str | None:
    clean = re.sub(r'[\s\u00a0\u202f]', '', raw).replace(',', '.')
    try:
        value = Decimal(clean)
        if not value.is_finite():
            return None
        return format(value, 'f')
    except (InvalidOperation, ValueError):
        return None


def _parsed_candidate(field: str, match: re.Match, text: str) -> tuple[str | None, str, str, str]:
    """Return (value, unit, validity, reason); no semantic legal interpretation."""
    raw = match.group('value')
    if field == 'deadline':
        try:
            dd, mm, yyyy = (int(x) for x in raw.split('.'))
            if not 2000 <= yyyy <= 2100:
                raise ValueError('year outside supported range')
            return date(yyyy, mm, dd).isoformat(), 'date', 'parsed', 'explicit_dd.mm.yyyy'
        except ValueError:
            return None, 'date', 'invalid', 'invalid_calendar_date'
    if field == 'duration':
        number = int(raw)
        if not 1 <= number <= 3650:
            return None, 'duration', 'invalid', 'invalid_duration'
        period = match.group('kind').lower()
        if period.startswith('месяц'):
            return str(number), 'months', 'parsed', 'explicit_months'
        unit = (match.group('unit') or '').lower()
        if unit == 'рабочих':
            return str(number), 'work_days', 'parsed', 'explicit_work_days'
        if unit == 'календарных':
            return str(number), 'calendar_days', 'parsed', 'explicit_calendar_days'
        return str(number), 'days_unspecified', 'candidate-only', 'day_type_not_specified'
    if field in {'advance_percent', 'retention_percent'}:
        value = _decimal(raw)
        if value is None or not (Decimal('0') <= Decimal(value) <= Decimal('100')):
            return None, 'percent', 'invalid', 'percent_out_of_range'
        # Share exactly the same polarity logic with rule findings. A negative
        # may occur after descriptive words, far beyond a fixed 38-char window.
        family = 'advance' if field == 'advance_percent' else 'retention'
        polarity, basis = classify(family, text, *match.span())
        if basis == 'quotation_or_previous_revision_requires_manual_review':
            return value, 'percent', 'historical', 'previous_revision_or_quoted_example'
        if polarity == 'explicit_negative':
            return value, 'percent', 'candidate-only', 'possible_negated_clause'
        if polarity == 'unclear':
            return value, 'percent', 'candidate-only', basis
        return value, 'percent', 'parsed', 'explicit_percent_candidate_context_checked'
    if field == 'budget_rub':
        value = _decimal(raw)
        if value is None or Decimal(value) <= 0:
            return None, 'RUB', 'invalid', 'invalid_amount'
        currency = (match.group('currency') or '').strip().lower()
        prefix = match.group('prefix') or ''
        after = text[match.end():match.end() + 8].lstrip()
        if after.startswith('%'):
            return value, 'RUB', 'candidate-only', 'amount_looks_like_percent'
        if (re.fullmatch(r'\d{1,2}\.\d{1,2}', raw) and after.startswith('.')):
            return value, 'RUB', 'candidate-only', 'section_number_not_amount'
        if _CONDITIONAL.search(prefix):
            return value, 'RUB', 'candidate-only', 'conditional_price'
        if not currency:
            return value, 'RUB', 'candidate-only', 'currency_not_explicit'
        return value, 'RUB', 'parsed', 'explicit_currency_rub'
    raise ValueError('unsupported field')


def _make_evidence(doc: dict, page: dict, match: re.Match, field: str) -> dict:
    text = page['text']
    start, end = match.span()
    eid_seed = f"{doc['sha256']}|{page['page']}|{field}|{start}|{end}".encode('utf-8')
    evidence_id = 'TF-' + hashlib.sha256(eid_seed).hexdigest()[:20]
    a, b = max(0, start - 45), min(len(text), end + 45)
    return {'id': evidence_id, 'file': doc['file'], 'source_sha256': doc['sha256'],
            'page': page['page'], 'normalized_span': [start, end],
            'span_basis': 'normalized_page_text',
            'match': text[start:end], 'quote': text[a:b]}


def extract_typed_fields(documents: list[dict]) -> dict:
    """Return stable typed candidates plus fail-closed statuses. No filesystem IO."""
    output = {}
    has_unreadable_pages = any(not page.get('has_text', bool(page.get('text')))
                               for doc in documents for page in doc['pages'])
    for field, default_unit, pattern in SPECS:
        candidates = []
        for doc in documents:
            for page in doc['pages']:
                text = page.get('text') or ''
                for hit in pattern.finditer(text):
                    value, unit, validity, reason = _parsed_candidate(field, hit, text)
                    if field == 'budget_rub' and reason in {'amount_looks_like_percent', 'section_number_not_amount'}:
                        continue
                    proof = _make_evidence(doc, page, hit, field)
                    candidates.append({'value': value, 'unit': unit, 'validity': validity,
                                       'reason': reason, 'evidence': proof})
        candidates.sort(key=lambda x: (x['evidence']['file'].casefold(),
                                       x['evidence']['source_sha256'],
                                       x['evidence']['page'],
                                       x['evidence']['normalized_span'][0]))
        # Historical/quoted candidates remain evidence, not active values.
        active = [c for c in candidates if c['validity'] != 'historical']
        parsed = [c for c in active if c['validity'] == 'parsed']
        combinations = {(c['value'], c['unit']) for c in parsed}
        all_unambiguous = bool(parsed) and len(parsed) == len(active) and len(combinations) == 1
        opposing_advance = field == 'advance_percent' and any(
            c['polarity'] == 'explicit_negative'
            for c in advance_conditions(documents))
        if all_unambiguous and not has_unreadable_pages and not opposing_advance:
            status, value, unit, basis = 'extracted', parsed[0]['value'], parsed[0]['unit'], 'explicit_pattern_and_unit'
        elif candidates:
            status, value, unit, basis = 'ambiguous', None, default_unit, (
                'opposing_advance_wording_requires_review' if opposing_advance
                else 'candidate_conflict_or_incomplete_context')
        elif has_unreadable_pages:
            status, value, unit, basis = 'ocr-required', None, default_unit, 'some_pages_have_no_searchable_text'
        else:
            status, value, unit, basis = 'not-found', None, default_unit, 'no_matching_explicit_clause'
        evidence = [c['evidence'] for c in candidates]
        output[field] = {
            'status': status, 'value': value, 'unit': unit,
            'confidence_basis': basis,
            'evidence_ids': [e['id'] for e in evidence],
            'evidence': evidence, 'candidates': candidates,
        }
    return output
