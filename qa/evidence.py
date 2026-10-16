"""Evidence integrity audit for the *allowed dev* pipeline's normalized pages.

This checks whether a candidate quote/span and SHA point to its input document;
not whether the extracted legal/commercial claim is true.
"""
from __future__ import annotations
from collections import Counter
import math


def audit(output):
    layout={d['file']:d for d in output.get('layout',[])}
    failures=[];checks=Counter(); facts=output.get('fast_dev2',{}).get('facts',[])
    for n,f in enumerate(facts):
        ev=f.get('evidence') or {};name=ev.get('file');doc=layout.get(name)
        checks['facts_seen']+=1
        if doc is None:
            failures.append({'index':n,'error':'missing_document','file':name});continue
        if ev.get('source_sha256')!=doc.get('sha256'):
            failures.append({'index':n,'error':'sha_mismatch','file':name});continue
        checks['sha_pass']+=1
        pg=ev.get('page')
        pages={p['page']:p for p in doc.get('pages',[])}
        if pg not in pages:
            failures.append({'index':n,'error':'invalid_page','file':name});continue
        checks['page_pass']+=1
        text=pages[pg].get('text','')
        span=ev.get('normalized_span')
        if not (isinstance(span,list) and len(span)==2 and all(type(x)==int for x in span) and 0<=span[0]<span[1]<=len(text)):
            failures.append({'index':n,'error':'invalid_span','file':name});continue
        if text[span[0]:span[1]]!=ev.get('match'):
            failures.append({'index':n,'error':'span_mismatch','file':name});continue
        checks['span_pass']+=1
        quote=ev.get('quote','')
        if not quote or ev['match'] not in quote:
            failures.append({'index':n,'error':'invalid_quote','file':name});continue
        checks['quote_pass']+=1
        bbox=ev.get('bbox')
        if bbox is not None and (not isinstance(bbox,list) or len(bbox)!=4 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in bbox) or bbox[2]<bbox[0] or bbox[3]<bbox[1]):
            failures.append({'index':n,'error':'invalid_bbox','file':name});continue
        checks['bbox_valid_or_unavailable']+=1
    return {'schema':'tenderlens.qa.evidence.v1','dataset_kind':'dev_synthetic',
            'checks':dict(checks),'errors':failures,'pass':not failures,
            'warning':'Evidence integrity is NOT ground truth accuracy or revision attestation.'}
