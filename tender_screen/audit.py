"""M04: immutable-in-spirit evidence registry and auditable export contract.

No external lookups; an evidence ID identifies wording in a particular input
PDF, not legal truth. A raw quote stays in JSON and is not trusted HTML/CSV.
"""
from __future__ import annotations

import hashlib
import json


def _stable_id(ev: dict) -> str:
    if ev.get('id'):
        return str(ev['id'])
    key = json.dumps([ev.get('source_sha256'), ev.get('page'),
                      ev.get('normalized_span'), ev.get('match')],
                     ensure_ascii=False, separators=(',', ':'))
    return 'EV-' + hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]


def finalize(result: dict, errors: list[dict], input_total: int) -> dict:
    """Attach a single registry to findings, fields, conditions and typed fields.

    IDs in every exported artifact resolve to the registry. Keep all pre-M04
    structures for backwards compatibility. Stable order is based on source
    data, not runtime timestamps, directories, or host-dependent ordering.
    """
    registry: dict[str, dict] = {}

    def attach(ev: dict, reference: str) -> None:
        ident = _stable_id(ev)
        ev['id'] = ident
        existing = registry.get(ident)
        location = (ev.get('file'), ev.get('source_sha256'), ev.get('page'),
                    ev.get('normalized_span'), ev.get('match'))
        if existing:
            old_location = (existing.get('file'), existing.get('source_sha256'),
                            existing.get('page'), existing.get('normalized_span'),
                            existing.get('match'))
            if location != old_location:
                raise ValueError('Evidence ID collision across different source locations')
            if reference not in existing['references']:
                existing['references'].append(reference)
            return
        row = {k: ev.get(k) for k in ('id', 'file', 'page', 'source_sha256',
               'match', 'quote', 'normalized_span', 'raw_span',
               'span_basis', 'span_status', 'polarity', 'polarity_basis')
               if k in ev}
        row['references'] = [reference]
        registry[ident] = row

    for finding in result.get('findings', []):
        for ev in finding.get('evidence', []):
            attach(ev, 'finding:' + finding['id'])
        finding['evidence_ids'] = [ev['id'] for ev in finding.get('evidence', [])]
    for field in result.get('fields', []):
        for ev in field.get('evidence', []):
            attach(ev, 'legacy_field:' + field['id'])
        field['evidence_ids'] = [ev['id'] for ev in field.get('evidence', [])]
    for code, field in result.get('typed_fields', {}).items():
        for ev in field.get('evidence', []):
            attach(ev, 'typed_field:' + code)
        for candidate in field.get('candidates', []):
            attach(candidate['evidence'], 'typed_field:' + code)
        field['evidence_ids'] = [ev['id'] for ev in field.get('evidence', [])]
    for key, term in result.get('terms', {}).items():
        for candidate in term.get('candidates', []):
            attach(candidate['evidence'], 'term:' + key)
        term['evidence_ids'] = [c['evidence']['id'] for c in term.get('candidates', [])]
    for condition in result.get('conditions', []):
        attach(condition['evidence'], 'condition:' + condition['family'])
        condition['evidence_id'] = condition['evidence']['id']
    for conflict in result.get('conflicts', []):
        for ev in conflict.get('evidence', []):
            attach(ev, 'conflict:' + conflict['family'])
        conflict['evidence_ids'] = [ev['id'] for ev in conflict.get('evidence', [])]

    documents = {d['file']: d for d in result.get('documents', [])}
    evidence = sorted(registry.values(), key=lambda ev: (
        (ev.get('file') or '').casefold(), ev.get('source_sha256') or '',
        ev.get('page') or 0, tuple(ev.get('normalized_span') or [0,0]), ev['id']))
    for entry in evidence:
        if entry.get('file') not in documents:
            raise ValueError('Evidence without source document')
        doc = documents[entry['file']]
        if entry.get('source_sha256') != doc.get('sha256'):
            raise ValueError('Evidence SHA256 does not match document')
        page = entry.get('page')
        if not isinstance(page, int) or page < 1 or page > doc.get('page_count', 0):
            raise ValueError('Invalid evidence page')
        entry['references'].sort()
    if result.get('conflicts'):
        for conflict in result['conflicts']:
            if not all(eid in registry for eid in conflict['evidence_ids']):
                raise ValueError('Conflict references missing evidence')
    if result.get('typed_fields'):
        for field in result['typed_fields'].values():
            if not all(eid in registry for eid in field['evidence_ids']):
                raise ValueError('Typed field references missing evidence')

    result['schema_version'] = '1.0.0'
    result['processing_status'] = ('failed' if not documents else 'partial' if errors else 'complete')
    result['input_files_total'] = input_total
    result['errors'] = sorted(errors, key=lambda e: (e['file'].casefold(), e['code']))
    result['evidence'] = evidence
    result['export_contract'] = {'evidence_ids': 'stable_in_current_input_set',
                                 'csv_formula_safety': 'spreadsheet_text_prefix_applied',
                                 'legal_compliance_verified': False}
    return result
