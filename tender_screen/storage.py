"""M06: offline SQLite, append-only human reviews, safe SHA-dedup intake.

User-selected root only. No networking. No implicit edits of original PDF.
Import is transaction/rollback safe for normal exceptions; power-loss orphan files
can remain and are intentionally never auto-deleted.
"""
from __future__ import annotations
import csv
from datetime import datetime, timezone
import hashlib
from html import escape
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import uuid
import pymupdf

from .core import analyze_folder
from .pack import build_pack_manifest, compare_pack
from .processing_budget import ProcessingBudget
from .security import validate_local_pdf, is_private_data_root

SCHEMA = 'analysis-v2'
MAX_FILE = 30*1024*1024
MAX_BATCH = 50


def _now():return datetime.now(timezone.utc).isoformat()

def _json(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def _sha(raw):return hashlib.sha256(raw).hexdigest()

def _csv_cell(value):
    s=str(value) if value is not None else ''
    # CSV injection on spreadsheet open, even after whitespace.
    return "'"+s if s.lstrip().startswith(('=','+','-','@','\t','\r')) else s


def _ensure_root(root):
    raw=Path(root).expanduser()
    if raw.is_symlink():raise ValueError('symlink_data_root_not_allowed')
    path=raw.resolve()
    path.mkdir(parents=True,exist_ok=True)
    if path.is_symlink():raise ValueError('symlink_data_root_not_allowed')
    path.chmod(0o700)
    return path


class LocalStore:
    def __init__(self, root):
        self.root=_ensure_root(root)
        is_private_data_root(self.root)
        self.blobs=self.root/'pdf_blobs';self.blobs.mkdir(exist_ok=True)
        self.blobs.chmod(0o700)
        self.db_path=self.root/'tenderlens.sqlite3'
        if self.db_path.is_symlink():raise ValueError('db_symlink_not_allowed')
        self.db=sqlite3.connect(self.db_path)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA busy_timeout=5000')
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.migrate()
    def __enter__(self):return self
    def __exit__(self,*args):self.db.close()
    def migrate(self):
        # initial migration; reopening is idempotent
        cur=self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
        present=cur.fetchone() is not None
        if not present:
            script=(Path(__file__).parent/'migrations'/'001_schema.sql').read_text(encoding='utf-8')
            self.db.executescript(script)
            with self.db:self.db.execute('INSERT INTO schema_migrations VALUES(?,?)',(1,_now()))
        else:
            v=self.db.execute('SELECT MAX(version) AS v FROM schema_migrations').fetchone()['v']
            if v!=1:raise ValueError('unsupported_schema_version')
    def project(self,name):
        name=name.strip()
        if not name or len(name)>100:raise ValueError('invalid_project_name')
        with self.db:self.db.execute('INSERT OR IGNORE INTO projects(name,created_utc) VALUES (?,?)',(name,_now()))
        return self.db.execute('SELECT id FROM projects WHERE name=?',(name,)).fetchone()['id']
    def projects(self):return [dict(x) for x in self.db.execute('SELECT * FROM projects ORDER BY id')]
    def _pid(self,project):
        row=self.db.execute('SELECT id FROM projects WHERE name=?',(project,)).fetchone()
        if row is None:raise ValueError('unknown_project')
        return row['id']
    def documents(self,project):
        pid=self._pid(project)
        return [dict(r) for r in self.db.execute('SELECT * FROM documents WHERE project_id=? ORDER BY id',(pid,))]
    def import_pdfs(self,project,paths,metadata=None):
        pid=self._pid(project)
        paths=[Path(x).expanduser() for x in paths]
        metadata=metadata or {}
        if not paths or len(paths)>MAX_BATCH:raise ValueError('invalid_import_batch_count')
        prepared=[];seen=set()
        # Preflight all paths before modifying DB or permanent blob storage.
        for p in paths:
            validate_local_pdf(p)
            if p.stat().st_size>MAX_FILE:raise ValueError('pdf_file_byte_limit_exceeded')
            if not p.name or '/' in p.name or '\\' in p.name:raise ValueError('invalid_pdf_basename')
            h=hashlib.sha256();size=0
            with p.open('rb') as f:
                prefix=f.read(5)
                if prefix!=b'%PDF-':raise ValueError('not_a_pdf_file')
                f.seek(0)
                for block in iter(lambda:f.read(1024*1024),b''):
                    size+=len(block);h.update(block)
            sha=h.hexdigest()
            if sha in seen:continue
            seen.add(sha)
            with pymupdf.open(p) as pdf:
                if pdf.needs_pass or len(pdf)<1:raise ValueError('encrypted_or_empty_pdf')
                pages=len(pdf)
            hint=metadata.get(p.name,{})
            if set(hint)-{'revision','effective','scope'}:raise ValueError('invalid_metadata_field')
            effective=hint.get('effective','unknown')
            if effective not in ('historical','current','unknown'):raise ValueError('invalid_effective_status')
            prepared.append((p,sha,size,pages,hint))
        created=[];imports=[];already=[]
        with tempfile.TemporaryDirectory(prefix='tl_stage_',dir=self.root) as stage:
            stage=Path(stage)
            for p,sha,size,pages,hint in prepared:
                target=stage/(sha+'.pdf')
                shutil.copyfile(p,target)
                if target.stat().st_size!=size or _file_sha(target)!=sha:raise ValueError('staging_sha_mismatch')
            try:
                self.db.execute('BEGIN IMMEDIATE')
                for p,sha,size,pages,hint in prepared:
                    existing=self.db.execute('SELECT id FROM documents WHERE project_id=? AND sha256=?',(pid,sha)).fetchone()
                    if existing:
                        already.append(existing['id']);continue
                    rel='pdf_blobs/'+sha+'.pdf';dest=self.root/rel
                    if dest.is_symlink():raise ValueError('blob_symlink_not_allowed')
                    if dest.exists():
                        if _file_sha(dest)!=sha:raise ValueError('blob_collision')
                    else:
                        os.replace(stage/(sha+'.pdf'),dest)
                        dest.chmod(0o600);created.append(dest)
                    cur=self.db.execute('''INSERT INTO documents(project_id,logical_name,sha256,stored_relpath,
                        byte_size,role_json,revision,effective,scope,imported_utc)
                        VALUES (?,?,?,?,?,?,?,?,?,?)''',
                        (pid,p.name,sha,rel,size,_json({'primary':'unknown','basis':'not_yet_analyzed'}),
                         str(hint.get('revision','unknown')),hint.get('effective','unknown'),
                         str(hint.get('scope','unknown')),_now()))
                    imports.append(cur.lastrowid)
                    # pages are known but have no normalized text until an analysis run.
                    for page in range(1,pages+1):
                        self.db.execute('INSERT INTO pages VALUES (?,?,?)',(cur.lastrowid,page,'pending_analysis'))
                self.db.commit()
            except BaseException:
                self.db.rollback()
                for target in created:
                    target.unlink(missing_ok=True)
                raise
        return {'imported_ids':imports,'deduplicated_ids':already,'count_added':len(imports),'count_existing':len(already)}

    def analyze_project(self,project,budget=None):
        pid=self._pid(project)
        all_docs=self.documents(project)
        if not all_docs:raise ValueError('no_project_documents')
        # Latest *local import* by exact filename (not legally current revision).
        chosen={}
        for d in all_docs:chosen[d['logical_name']]=d
        selected=sorted(chosen.values(),key=lambda x:x['logical_name'])
        if len(selected)>MAX_BATCH:raise ValueError('too_many_documents')
        with tempfile.TemporaryDirectory(prefix='tl_analysis_',dir=self.root) as work:
            work=Path(work)
            for d in selected:
                src=self.root/d['stored_relpath']; dst=work/d['logical_name']
                if src.is_symlink() or not src.is_file() or _file_sha(src)!=d['sha256']:
                    raise ValueError('stored_pdf_missing_or_tampered')
                shutil.copyfile(src,dst)
            # Retains original FD2 JSON keys; M05 is an additive layer only.
            output=analyze_folder(work,budget=budget or ProcessingBudget())
        layout=output.get('layout',[])
        for d in selected:
            matches=[r for r in layout if r['file']==d['logical_name']]
            if not matches:continue
            if matches[0]['sha256']!=d['sha256']:raise ValueError('analysis_sha_mismatch')
            matches[0]['document_role']=matches[0].get('document_role') or {'primary':'unknown'}
        hints={d['logical_name']:{'revision':d['revision'],'effective':d['effective'],'scope':d['scope']} for d in selected}
        manifest=build_pack_manifest(layout,hints)
        pack=compare_pack(manifest,output['fast_dev2'],layout)
        m05={'manifest':manifest,'comparison':pack}
        output['fast_dev3']=m05
        status=output.get('processing_status','unknown')
        with self.db:
            prev=self.db.execute('SELECT id FROM runs WHERE project_id=? ORDER BY id DESC LIMIT 1',(pid,)).fetchone()
            cur=self.db.execute('''INSERT INTO runs(project_id,parent_run_id,created_utc,selection,status,full_result_json,analysis_schema)
                 VALUES (?,?,?,?,?,?,?)''',(pid,prev['id'] if prev else None,_now(),
                 'latest_local_import_per_filename_not_official_current',status,_json(output),SCHEMA))
            run_id=cur.lastrowid
            for d in selected:self.db.execute('INSERT INTO run_documents VALUES (?,?)',(run_id,d['id']))
            for doc in layout:
                origin=next(x for x in selected if x['sha256']==doc['sha256'])
                self.db.execute('UPDATE documents SET role_json=? WHERE id=?',(_json(doc['document_role']),origin['id']))
                for p in doc.get('pages',[]):
                    self.db.execute('UPDATE pages SET text_sha256=? WHERE document_id=? AND page_number=?',
                        (_sha(p['text'].encode()),origin['id'],p['page']))
            for f in output['fast_dev2']['facts']:
                self.db.execute('''INSERT INTO claims(run_id,field_kind,machine_value_json,unit,evidence_json,candidate_status,doc_sha256)
                     VALUES (?,?,?,?,?,?,?)''',(run_id,f['kind'],_json(f.get('value')),f.get('unit'),
                     _json(f['evidence']),f['status'],f['evidence']['source_sha256']))
            for q in pack['questions']:
                self.db.execute('INSERT INTO review_questions(run_id,question_key,payload_json) VALUES (?,?,?)',
                    (run_id,q['id'],_json(q)))
        return {'run_id':run_id,'status':status,'documents':len(selected),'facts':len(output['fast_dev2']['facts']),
                'review_questions':len(pack['questions']),'manifest':manifest}

    def runs(self,project):
        pid=self._pid(project)
        return [dict(r) for r in self.db.execute('SELECT id,parent_run_id,created_utc,selection,status FROM runs WHERE project_id=? ORDER BY id',(pid,))]
    def questions(self,run_id):
        return [{'local_question_id':r['id'],'question_key':r['question_key'],
                 'status':'resolved_by_user' if self.db.execute('SELECT 1 FROM question_resolutions WHERE question_id=? LIMIT 1',(r['id'],)).fetchone() else 'unresolved',
                 'payload':json.loads(r['payload_json'])}
                for r in self.db.execute('SELECT * FROM review_questions WHERE run_id=? ORDER BY id',(run_id,))]
    def compare_runs(self,old_run_id,new_run_id):
        old=self._run_view(old_run_id);new=self._run_view(new_run_id)
        if old['project_id']!=new['project_id']:raise ValueError('cannot_compare_different_projects')
        def docs(run_id):
            rows=self.db.execute("SELECT d.logical_name,d.sha256 FROM run_documents rd JOIN documents d ON d.id=rd.document_id WHERE rd.run_id=?",(run_id,))
            return {r['logical_name']:r['sha256'] for r in rows}
        before=docs(old_run_id);after=docs(new_run_id)
        names=sorted(set(before)|set(after))
        return {'schema':'tenderlens.run_diff.v1','old_run_id':old_run_id,'new_run_id':new_run_id,
                'document_changes':[{'filename':n,'old_sha256':before.get(n),'new_sha256':after.get(n),
                                     'status':'added' if n not in before else 'removed' if n not in after else 'changed' if before[n]!=after[n] else 'unchanged'}
                                    for n in names],
                'facts_old':len(old['reviewed_claims']),'facts_new':len(new['reviewed_claims']),
                'caution':'import_time_not_source_effective_date; not_an_accuracy_metric'}
    def claims(self,run_id):
        return [dict(r) for r in self.db.execute('SELECT * FROM claims WHERE run_id=? ORDER BY id',(run_id,))]
    def review_claim(self,claim_id,corrected_value,comment,actor='local'):
        row=self.db.execute('SELECT id,evidence_json FROM claims WHERE id=?',(claim_id,)).fetchone()
        if not row:raise ValueError('unknown_claim')
        if not isinstance(actor,str) or not actor.strip() or len(actor)>60:raise ValueError('invalid_actor')
        if not isinstance(comment,str) or len(comment)>500:raise ValueError('invalid_review_comment')
        if corrected_value is not None and len(_json(corrected_value))>1000:raise ValueError('review_value_too_long')
        evsha=_sha(row['evidence_json'].encode())
        with self.db:
            cur=self.db.execute('''INSERT INTO reviews(claim_id,actor,corrected_value_json,comment,evidence_sha256,created_utc)
            VALUES (?,?,?,?,?,?)''',(claim_id,actor,_json(corrected_value),comment,evsha,_now()))
        return cur.lastrowid
    def resolve_question(self,question_id,note,actor='local'):
        exists=self.db.execute('SELECT id FROM review_questions WHERE id=?',(question_id,)).fetchone()
        if not exists:raise ValueError('unknown_question')
        if not isinstance(note,str) or not note.strip() or len(note)>2000:raise ValueError('resolution_note_required')
        if not actor.strip() or len(actor)>60:raise ValueError('invalid_actor')
        with self.db:
            cur=self.db.execute('INSERT INTO question_resolutions(question_id,actor,note,created_utc) VALUES (?,?,?,?)',
                (question_id,actor,note,_now()))
        return cur.lastrowid
    def _run_view(self,run_id):
        run=self.db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
        if not run:raise ValueError('unknown_run')
        raw=json.loads(run['full_result_json']);claims=[]
        for c in self.db.execute('SELECT * FROM claims WHERE run_id=? ORDER BY id',(run_id,)):
            history=[dict(r) for r in self.db.execute('SELECT * FROM reviews WHERE claim_id=? ORDER BY id',(c['id'],))]
            machine=json.loads(c['machine_value_json'])
            reviews=[{'actor':r['actor'],'value':json.loads(r['corrected_value_json']),
                      'comment':r['comment'],'created_utc':r['created_utc'], 'evidence_sha256':r['evidence_sha256']}
                      for r in history]
            claims.append({'claim_id':c['id'],'kind':c['field_kind'],'machine_value':machine,
              'effective_value':reviews[-1]['value'] if reviews else machine,
              'origin':'human_review' if reviews else 'machine_candidate',
              'unit':c['unit'],'evidence':json.loads(c['evidence_json']), 'review_history':reviews})
        qs=[]
        for q in self.db.execute('SELECT * FROM review_questions WHERE run_id=? ORDER BY id',(run_id,)):
            resolutions=[dict(r) for r in self.db.execute('SELECT actor,note,created_utc FROM question_resolutions WHERE question_id=? ORDER BY id',(q['id'],))]
            val=json.loads(q['payload_json']);val['local_question_id']=q['id']
            val['status']='resolved_by_user' if resolutions else 'unresolved'
            val['resolutions']=resolutions
            qs.append(val)
        return {'schema_version':SCHEMA,'run_id':run_id,'project_id':run['project_id'],
                'created_utc':run['created_utc'],'selection':run['selection'],
                'parent_run_id':run['parent_run_id'],'machine_result':raw,
                'reviewed_claims':claims,'review_questions':qs,
                'warnings':['not_blind_accuracy','not_a_legal_verdict','no_auto_revision_priority']}
    def export(self,run_id,target_dir):
        requested=Path(target_dir).expanduser()
        if requested.is_symlink():raise ValueError('export_symlink_not_allowed')
        target_dir=requested.resolve()
        if target_dir.is_symlink():raise ValueError('export_symlink_not_allowed')
        target_dir.mkdir(parents=True,exist_ok=True)
        snapshot=self._run_view(run_id)
        # Unique versioned run export; no silent overwriting.
        basename=f'run_{run_id:04d}_{uuid.uuid4().hex[:8]}'
        dest=target_dir/basename;dest.mkdir(mode=0o700)
        (dest/'analysis-v2.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
        with (dest/'claims-v2.csv').open('w',newline='',encoding='utf-8-sig') as h:
            w=csv.writer(h);w.writerow(['claim_id','kind','machine_value','effective_value','origin','source_sha256','file','page','quote'])
            for row in snapshot['reviewed_claims']:
                e=row['evidence'];w.writerow([_csv_cell(row['claim_id']),_csv_cell(row['kind']),_csv_cell(row['machine_value']),
                     _csv_cell(row['effective_value']),row['origin'],e['source_sha256'],_csv_cell(e['file']),e['page'],_csv_cell(e['quote'])])
        rows=[]
        for row in snapshot['reviewed_claims']:
            e=row['evidence']
            t=[row['kind'],row['machine_value'],row['effective_value'],row['origin'],e['file'],e['page'],e['quote']]
            rows.append('<tr>'+''.join('<td>'+escape(str(x if x is not None else ''))+'</td>' for x in t)+'</tr>')
        html='''<!doctype html><html lang="ru"><meta charset="utf-8"><title>TenderLens analysis-v2</title><style>body{font:14px system-ui;margin:30px}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:8px}td{vertical-align:top}</style><h1>Локальные факты и ручные правки</h1><p>Не юридическое заключение. Редакции неизвестны. Исправления человека не переписывают машинные данные.</p><table><tr><th>Поле</th><th>Машина</th><th>Текущая правка</th><th>Источник</th><th>Файл</th><th>Стр.</th><th>Цитата</th></tr>'''+''.join(rows)+'</table></html>'
        (dest/'analysis-v2.html').write_text(html,encoding='utf-8')
        return dest


def _file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
