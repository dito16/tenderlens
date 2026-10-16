"""Bounded subprocess boundary for untrusted PDF analysis.

Uses a fresh process for each analysis; the API parent enforces a hard timeout.
LocalStore provides atomic writes and migrations; no external network.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from ..storage import LocalStore
from .service import project_name

def run(root:Path,project_id:int):
    with LocalStore(root) as db:
        return db.analyze_project(project_name(db,project_id))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--project-id',type=int,required=True)
    args=parser.parse_args()
    try:
        print('TENDERLENS_WORKER_JSON:'+json.dumps({'ok':True,'result':run(args.data_root,args.project_id)},ensure_ascii=False),flush=True)
    except (ValueError,RuntimeError) as exc:
        print('TENDERLENS_WORKER_JSON:'+json.dumps({'ok':False,'error':str(exc)[:180]},ensure_ascii=False),flush=True)
        sys.exit(2)

if __name__=='__main__':main()
