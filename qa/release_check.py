"""Strict, offline, fail-closed prepublication tree scan. Not a security audit."""
from __future__ import annotations
from pathlib import Path
import argparse
import hashlib
import json
import re

DENIED_NAMES={'.env','.env.local','.git','__pycache__','.DS_Store','id_rsa','id_ed25519'}
DENIED_SUFFIXES={'.sqlite','.sqlite3','.db','.p12','.pem','.key','.pyc'}
TEXT_TYPES={'.py','.md','.sh','.txt','.toml','.json','.css','.js','.html','.sql','.gitignore'}
DENIED_CONTENT=[re.compile(x,re.I) for x in (r'/Users/[A-Za-z0-9_.-]+/',r'/mnt/data/',r'/home/oai/',
    r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'AKIA[0-9A-Z]{16}',
    r'TENDERLENS_G4_PRIVATE_RETURN',r'G4_TLS_RETRY_PRIVATE')]

def inspect(root):
    root=Path(root).resolve()
    problems=[];hashes=[];total_bytes=0
    for f in sorted(root.rglob('*')):
        relative=f.relative_to(root).as_posix()
        if f.name in DENIED_NAMES or any(parent in DENIED_NAMES for parent in f.relative_to(root).parts[:-1]):
            problems.append('denied_name:'+relative)
            continue
        if f.is_symlink():problems.append('symlink:'+relative);continue
        if not f.is_file():continue
        if f.suffix.lower() in DENIED_SUFFIXES:
            problems.append('private_file_type:'+relative);continue
        raw=f.read_bytes();total_bytes+=len(raw)
        if len(raw)>30*1024*1024:problems.append('oversize:'+relative)
        if (f.suffix in TEXT_TYPES or f.name=='.gitignore') and relative not in {'qa/release_check.py','tests/test_fast_dev6_release.py'}:
            # Self-tests contain only artificial dangerous markers; evaluate them separately.
            text=raw.decode('utf-8','replace')
            for regex in DENIED_CONTENT:
                if regex.search(text):problems.append('sensitive_marker:'+relative+':'+regex.pattern)
        hashes.append({'path':relative,'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)})
    return {'schema':'tenderlens.release.scan.v1','allowed_for_automatic_publication':False,
        'source_scan_pass':not problems,'problems':problems,'files':len(hashes),'bytes':total_bytes,'hashes':hashes,
        'remaining_manual_gates':['project_license','AGPL_compliance_review','independent_quality','author_approval','Mac_validation']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=inspect(a.root)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('SOURCE_TREE_SCAN='+('PASS' if r['source_scan_pass'] else 'FAIL')+' files='+str(r['files']))
    print('PUBLICATION=BLOCKED_PENDING_EXPLICIT_PERMISSION')
    if not r['source_scan_pass']:raise SystemExit(3)
if __name__=='__main__':main()
