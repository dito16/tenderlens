"""FAST DEV 3 local project CLI. Existing `python -m tender_screen run` unchanged."""
import argparse
import json
from pathlib import Path
from .storage import LocalStore


def main(argv=None):
    p=argparse.ArgumentParser(description='TenderLens offline project storage and review')
    p.add_argument('--data-root',required=True,type=Path,help='private user-selected folder for SQLite and imported PDFs')
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('create');a.add_argument('project')
    a=sub.add_parser('import');a.add_argument('project');a.add_argument('pdfs',nargs='+',type=Path)
    a.add_argument('--metadata',type=Path,help='optional JSON mapping filename -> revision/effective/scope')
    a=sub.add_parser('analyze');a.add_argument('project')
    a=sub.add_parser('projects')
    a=sub.add_parser('documents');a.add_argument('project')
    a=sub.add_parser('runs');a.add_argument('project')
    a=sub.add_parser('claims');a.add_argument('run_id',type=int)
    a=sub.add_parser('questions');a.add_argument('run_id',type=int)
    a=sub.add_parser('diff');a.add_argument('old_run_id',type=int);a.add_argument('new_run_id',type=int)
    a=sub.add_parser('review');a.add_argument('claim_id',type=int);a.add_argument('--value',required=True)
    a.add_argument('--comment',required=True)
    a=sub.add_parser('resolve');a.add_argument('question_id',type=int);a.add_argument('--note',required=True)
    a=sub.add_parser('export');a.add_argument('run_id',type=int);a.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    with LocalStore(args.data_root) as store:
        if args.command=='create':res={'project_id':store.project(args.project)}
        elif args.command=='import':
            metadata=json.loads(args.metadata.read_text(encoding='utf-8')) if args.metadata else None
            res=store.import_pdfs(args.project,args.pdfs,metadata)
        elif args.command=='analyze':res=store.analyze_project(args.project)
        elif args.command=='projects':res=store.projects()
        elif args.command=='documents':res=store.documents(args.project)
        elif args.command=='runs':res=store.runs(args.project)
        elif args.command=='claims':res=store.claims(args.run_id)
        elif args.command=='questions':res=store.questions(args.run_id)
        elif args.command=='diff':res=store.compare_runs(args.old_run_id,args.new_run_id)
        elif args.command=='review':res={'review_id':store.review_claim(args.claim_id,args.value,args.comment)}
        elif args.command=='resolve':res={'resolution_id':store.resolve_question(args.question_id,args.note)}
        else:res={'export_dir':str(store.export(args.run_id,args.output))}
    print(json.dumps(res,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
