"""M07 service facade: validates ownership, intake and evidence paths.

The facade deliberately has no Flask dependency to allow isolated regression tests.
"""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile
from ..storage import LocalStore, MAX_FILE, _file_sha
from ..security import validate_local_pdf

MAX_WEB_FILES = 10
MAX_WEB_TOTAL = 100 * 1024 * 1024

class UIInputError(ValueError):
    pass

def project_name(store: LocalStore, project_id: int) -> str:
    row=store.db.execute('SELECT name FROM projects WHERE id=?',(project_id,)).fetchone()
    if row is None: raise UIInputError('project_not_found')
    return row['name']

def owner_run(store: LocalStore, project_id: int, run_id: int):
    row=store.db.execute('SELECT id FROM runs WHERE id=? AND project_id=?',(run_id,project_id)).fetchone()
    if not row: raise UIInputError('run_not_in_project')
    return row['id']

def owner_claim(store: LocalStore, project_id: int, run_id: int, claim_id: int):
    owner_run(store,project_id,run_id)
    found=store.db.execute('''SELECT c.id FROM claims c JOIN runs r ON c.run_id=r.id
           WHERE c.id=? AND c.run_id=? AND r.project_id=?''',(claim_id,run_id,project_id)).fetchone()
    if not found: raise UIInputError('claim_not_in_run')

def owner_question(store: LocalStore, project_id: int, run_id: int, question_id: int):
    owner_run(store,project_id,run_id)
    found=store.db.execute('''SELECT q.id FROM review_questions q JOIN runs r ON q.run_id=r.id
           WHERE q.id=? AND q.run_id=? AND r.project_id=?''',(question_id,run_id,project_id)).fetchone()
    if not found: raise UIInputError('question_not_in_run')

def owner_doc_path(store: LocalStore, project_id: int, doc_id: int):
    found=store.db.execute('''SELECT stored_relpath,sha256 FROM documents
           WHERE id=? AND project_id=?''',(doc_id,project_id)).fetchone()
    if not found: raise UIInputError('document_not_in_project')
    # Only storage-managed name; never allow client-supplied paths.
    sha=found['sha256'];path=store.blobs/(sha+'.pdf')
    if found['stored_relpath']!='pdf_blobs/'+sha+'.pdf' or path.is_symlink() or not path.is_file():
        raise UIInputError('invalid_stored_document')
    if _file_sha(path)!=sha: raise UIInputError('stored_pdf_sha256_mismatch')
    return path

def run_state(store:LocalStore, project_id:int, run_id:int):
    owner_run(store,project_id,run_id)
    snapshot=store._run_view(run_id)
    return {'run_id':run_id,'created_utc':snapshot['created_utc'],
       'selection':snapshot['selection'],'status':snapshot['machine_result'].get('processing_status','unknown'),
       'claims':snapshot['reviewed_claims'],'questions':snapshot['review_questions'],
       'warnings':snapshot['warnings'],'parent_run_id':snapshot['parent_run_id']}

def document_list(store:LocalStore, project_id:int):
    name=project_name(store,project_id)
    return [{k:d[k] for k in ('id','logical_name','sha256','byte_size','revision','effective','scope')}
            for d in store.documents(name)]

def safe_import_streams(store: LocalStore, project_id:int, files):
    """Copy uploads to private staging with bounded streaming; refuse bad batches atomically."""
    name=project_name(store,project_id)
    if not files or len(files)>MAX_WEB_FILES: raise UIInputError('upload_count_1_to_10_required')
    seen=set(); total=0
    with tempfile.TemporaryDirectory(prefix='tl_web_in_',dir=store.root) as directory:
        stage=Path(directory); paths=[]
        for item in files:
            fname=item.filename or ''
            if (not fname or fname in seen or len(fname)>180 or
                '/' in fname or '\\' in fname or fname.startswith('.') or
                fname.lower().endswith('.pdf') is False or '\x00' in fname):
                raise UIInputError('invalid_or_duplicate_pdf_filename')
            seen.add(fname); target=stage/fname;size=0
            with target.open('xb') as dest:
                while True:
                    data=item.stream.read(1024*1024)
                    if not data:break
                    size+=len(data); total+=len(data)
                    if size>MAX_FILE or total>MAX_WEB_TOTAL:
                        raise UIInputError('upload_size_limit_exceeded')
                    dest.write(data)
            if size<5:raise UIInputError('empty_or_short_pdf')
            try:validate_local_pdf(target)
            except ValueError as exc:raise UIInputError(str(exc)) from exc
            paths.append(target)
        return store.import_pdfs(name, paths)

def export_zip(store:LocalStore,project_id:int,run_id:int):
    owner_run(store,project_id,run_id)
    with tempfile.TemporaryDirectory(prefix='tl_web_export_',dir=store.root) as tmp:
        output=store.export(run_id,Path(tmp))
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for p in sorted(output.iterdir()):
                if not p.is_file() or p.is_symlink():raise UIInputError('invalid_export_file')
                archive.write(p,arcname=p.name)
        memory.seek(0);return memory

def json_review_value(raw: str):
    if len(raw)>1000: raise UIInputError('value_too_long')
    try:
        val=json.loads(raw)
    except (json.JSONDecodeError,ValueError):
        # JSON objects and lists are entered explicitly, ordinary strings remain strings.
        val=raw
    if isinstance(val,(dict,list)): raise UIInputError('complex_review_value_not_supported_by_UI')
    return val
