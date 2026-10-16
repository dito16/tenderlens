"""M07 local-only Flask app: explicit browser token, no external assets or networking.

Use `python -m tender_screen.web.run`, which binds loopback only. Not for LAN or
public hosting. A random CSRF token is issued on every startup; mutations require it.
"""
from __future__ import annotations
import os
import subprocess
import sys
import json
from pathlib import Path
import re
import secrets
from flask import Flask, abort, jsonify, render_template, request, send_file, g
from werkzeug.exceptions import HTTPException
from ..security import is_private_data_root, WEB_ANALYZE_HARD_TIMEOUT_SECONDS
from ..storage import LocalStore
from .service import (UIInputError, project_name, owner_run, owner_claim,
     owner_question, owner_doc_path, run_state, document_list,
     safe_import_streams, export_zip, json_review_value, MAX_WEB_TOTAL)

LOCAL_HOSTS={'localhost','127.0.0.1'}

def create_app(data_root):
    if not data_root: raise ValueError('private_data_root_required')
    raw=Path(data_root).expanduser()
    is_private_data_root(raw)
    app=Flask(__name__,template_folder='templates',static_folder='static')
    app.config.update(MAX_CONTENT_LENGTH=MAX_WEB_TOTAL+1024*1024,
                      JSON_AS_ASCII=False,SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Strict')
    app.config['TL_DATA_ROOT']=str(Path(data_root).expanduser().resolve())
    app.config['TL_CSRF']=secrets.token_urlsafe(32)
    app.config['TESTING']=False

    @app.before_request
    def gate():
        # Do not allow Host-based DNS rebinding to a local-only service.
        host=request.host.split(':',1)[0].lower()
        if host not in LOCAL_HOSTS:abort(403,description='unsupported_host')
        if request.method in ('POST','PUT','PATCH','DELETE'):
            submitted=request.headers.get('X-TenderLens-CSRF') or request.form.get('csrf_token')
            if not submitted or not secrets.compare_digest(submitted,app.config['TL_CSRF']):
                abort(403,description='csrf_missing_or_invalid')
        g.store=LocalStore(app.config['TL_DATA_ROOT'])

    @app.teardown_request
    def close(exc):
        store=getattr(g,'store',None)
        if store is not None:store.db.close()

    @app.after_request
    def secure(resp):
        resp.headers['X-Content-Type-Options']='nosniff'
        resp.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
        resp.headers['Cross-Origin-Opener-Policy']='same-origin'
        resp.headers['Referrer-Policy']='no-referrer'
        resp.headers['X-Frame-Options']='SAMEORIGIN'
        resp.headers['Cache-Control']='no-store'
        resp.headers['Cross-Origin-Resource-Policy']='same-origin'
        resp.headers['Content-Security-Policy']=(
           "default-src 'self'; script-src 'self'; style-src 'self'; "
           "img-src 'self' data:; connect-src 'self'; frame-src 'self'; "
           "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'")
        return resp

    @app.errorhandler(UIInputError)
    @app.errorhandler(ValueError)
    def input_error(error):
        return jsonify(error=str(error),ok=False),400

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description,ok=False),error.code

    @app.errorhandler(Exception)
    def unknown(error):
        app.logger.exception('TenderLens web request failed')
        return jsonify(error='internal_error_see_local_log',ok=False),500

    def body():
        if not request.is_json:abort(415,description='application_json_required')
        obj=request.get_json(silent=True)
        if not isinstance(obj,dict):abort(400,description='json_object_required')
        return obj

    def as_int(value):
        try:return int(value)
        except (ValueError,TypeError):raise UIInputError('invalid_integer_id')

    @app.get('/')
    def home():return render_template('index.html',csrf=app.config['TL_CSRF'])

    @app.get('/api/health')
    def health():return jsonify(ok=True,mode='offline_loopback_only',schema='analysis-v2')

    @app.get('/api/projects')
    def projects():return jsonify(projects=g.store.projects())

    @app.post('/api/projects')
    def add_project():
        name=body().get('name','')
        if not isinstance(name,str):raise UIInputError('invalid_project_name')
        return jsonify(project_id=g.store.project(name)),201

    @app.get('/api/projects/<int:project_id>')
    def project_state(project_id):
        name=project_name(g.store,project_id)
        return jsonify(project={'id':project_id,'name':name},
                       documents=document_list(g.store,project_id),
                       runs=g.store.runs(name))

    @app.post('/api/projects/<int:project_id>/documents')
    def import_pdfs(project_id):
        files=request.files.getlist('pdfs')
        result=safe_import_streams(g.store,project_id,files)
        return jsonify(result),201

    @app.post('/api/projects/<int:project_id>/analyze')
    def analyze(project_id):
        # Native PDF parsing is isolated in a child process with a hard time limit.
        project_name(g.store,project_id)
        command=[sys.executable,'-m','tender_screen.web.worker','--data-root',
                 app.config['TL_DATA_ROOT'],'--project-id',str(project_id)]
        try:
            ret=subprocess.run(command,capture_output=True,text=True,timeout=WEB_ANALYZE_HARD_TIMEOUT_SECONDS,
                 cwd=str(Path(__file__).resolve().parents[2]),check=False)
        except subprocess.TimeoutExpired:
            return jsonify(ok=False,error='analysis_hard_timeout_no_complete_run'),503
        if len(ret.stdout)>128*1024 or ret.returncode not in (0,2):
            return jsonify(ok=False,error='analysis_worker_failed'),500
        try:
            responses=[x.split('TENDERLENS_WORKER_JSON:',1)[1] for x in ret.stdout.splitlines() if x.startswith('TENDERLENS_WORKER_JSON:')]
            response=json.loads(responses[-1]) if len(responses)==1 else None
        except (ValueError,TypeError):
            return jsonify(ok=False,error='analysis_worker_invalid_response'),500
        if not isinstance(response,dict):
            return jsonify(ok=False,error='analysis_worker_invalid_response'),500
        if not response.get('ok'):
            return jsonify(ok=False,error=response.get('error','analysis_failed')),400
        return jsonify(response['result']),201

    @app.get('/api/projects/<int:project_id>/runs/<int:run_id>')
    def run_details(project_id,run_id):
        return jsonify(run_state(g.store,project_id,run_id))

    @app.post('/api/projects/<int:project_id>/runs/<int:run_id>/claims/<int:claim_id>/review')
    def review_claim(project_id,run_id,claim_id):
        owner_claim(g.store,project_id,run_id,claim_id)
        obj=body(); comment=obj.get('comment','')
        if not isinstance(comment,str) or not comment.strip():raise UIInputError('review_comment_required')
        value=obj.get('value')
        if not isinstance(value,str):raise UIInputError('review_value_must_be_string')
        return jsonify(review_id=g.store.review_claim(claim_id,json_review_value(value),comment)),201

    @app.post('/api/projects/<int:project_id>/runs/<int:run_id>/questions/<int:qid>/resolve')
    def resolve_question(project_id,run_id,qid):
        owner_question(g.store,project_id,run_id,qid)
        obj=body(); note=obj.get('note')
        if not isinstance(note,str):raise UIInputError('invalid_resolution_note')
        return jsonify(resolution_id=g.store.resolve_question(qid,note)),201

    @app.get('/api/projects/<int:project_id>/documents/<int:doc_id>/pdf')
    def pdf_viewer(project_id,doc_id):
        p=owner_doc_path(g.store,project_id,doc_id)
        resp=send_file(p,mimetype='application/pdf',as_attachment=False,
                       download_name='document.pdf',conditional=False)
        resp.headers['Content-Disposition']='inline; filename="document.pdf"'
        return resp

    @app.get('/api/projects/<int:project_id>/runs/<int:run_id>/export')
    def export(project_id,run_id):
        memory=export_zip(g.store,project_id,run_id)
        return send_file(memory,mimetype='application/zip',as_attachment=True,
                         download_name=f'tenderlens_run_{run_id}.zip')

    @app.get('/api/projects/<int:project_id>/runs/<int:run_a>/diff/<int:run_b>')
    def compare(project_id,run_a,run_b):
        owner_run(g.store,project_id,run_a)
        owner_run(g.store,project_id,run_b)
        return jsonify(g.store.compare_runs(run_a,run_b))

    return app
