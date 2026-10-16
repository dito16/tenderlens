PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS projects(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(
 id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 logical_name TEXT NOT NULL, sha256 TEXT NOT NULL, stored_relpath TEXT NOT NULL,
 byte_size INTEGER NOT NULL, role_json TEXT NOT NULL, revision TEXT NOT NULL DEFAULT 'unknown',
 effective TEXT NOT NULL DEFAULT 'unknown' CHECK(effective IN ('unknown','historical','current')),
 scope TEXT NOT NULL DEFAULT 'unknown', imported_utc TEXT NOT NULL,
 UNIQUE(project_id,sha256));
CREATE INDEX IF NOT EXISTS idx_documents_project_name ON documents(project_id,logical_name,id);
CREATE TABLE IF NOT EXISTS pages(
 document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 page_number INTEGER NOT NULL, text_sha256 TEXT NOT NULL, PRIMARY KEY(document_id,page_number));
CREATE TABLE IF NOT EXISTS runs(
 id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id),
 parent_run_id INTEGER REFERENCES runs(id),created_utc TEXT NOT NULL,
 selection TEXT NOT NULL, status TEXT NOT NULL,
 full_result_json TEXT NOT NULL, analysis_schema TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id,id);
CREATE TABLE IF NOT EXISTS run_documents(
 run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
 document_id INTEGER NOT NULL REFERENCES documents(id),
 PRIMARY KEY(run_id,document_id));
CREATE TABLE IF NOT EXISTS claims(
 id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
 field_kind TEXT NOT NULL, machine_value_json TEXT NOT NULL, unit TEXT,
 evidence_json TEXT NOT NULL, candidate_status TEXT NOT NULL, doc_sha256 TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_claims_run ON claims(run_id,id);
CREATE TABLE IF NOT EXISTS reviews(
 id INTEGER PRIMARY KEY,claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
 actor TEXT NOT NULL, corrected_value_json TEXT NOT NULL, comment TEXT NOT NULL,
 evidence_sha256 TEXT NOT NULL, created_utc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_reviews_claim ON reviews(claim_id,id);
CREATE TABLE IF NOT EXISTS review_questions(
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
 question_key TEXT NOT NULL, payload_json TEXT NOT NULL, UNIQUE(run_id,question_key));
CREATE TABLE IF NOT EXISTS question_resolutions(
 id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL REFERENCES review_questions(id),
 actor TEXT NOT NULL, note TEXT NOT NULL, created_utc TEXT NOT NULL);
