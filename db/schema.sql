-- interview_helper_mux — canonical SQLite store (single file, foreign keys on).
-- Apply via: sqlite3 path.db < db/schema.sql  OR Python mux_store.init_db()

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA application_id = 0x4d555831; -- 'MUX1'

-- ---------------------------------------------------------------------------
-- Schema bookkeeping
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Canonical pipeline backbone (DAG order). Optional parallel enrichments are
-- modeled as assets + run_step metadata, not duplicate stages.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS pipeline_stage (
  slug TEXT PRIMARY KEY,
  ordinal INTEGER NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  notes TEXT
);

-- ---------------------------------------------------------------------------
-- Repository docs (ideas, specs, indexes) — full text + structured front matter
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS doc_source (
  id INTEGER PRIMARY KEY,
  rel_path TEXT NOT NULL UNIQUE,
  domain TEXT NOT NULL,
  title TEXT,
  doc_slug TEXT,
  tier TEXT,
  status TEXT,
  front_matter_json TEXT NOT NULL,
  body_markdown TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  file_mtime_unix REAL,
  imported_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_doc_source_domain ON doc_source (domain);
CREATE INDEX IF NOT EXISTS idx_doc_source_slug ON doc_source (doc_slug);

-- depends_on from front matter: raw slug -> resolved doc row when matched
CREATE TABLE IF NOT EXISTS doc_dependency (
  id INTEGER PRIMARY KEY,
  from_doc_id INTEGER NOT NULL REFERENCES doc_source (id) ON DELETE CASCADE,
  depends_on_slug TEXT NOT NULL,
  to_doc_id INTEGER REFERENCES doc_source (id) ON DELETE SET NULL,
  UNIQUE (from_doc_id, depends_on_slug)
);

CREATE INDEX IF NOT EXISTS idx_doc_dep_from ON doc_dependency (from_doc_id);

-- Markdown links extracted from body (internal docs/ targets and http(s))
CREATE TABLE IF NOT EXISTS doc_outbound_link (
  id INTEGER PRIMARY KEY,
  from_doc_id INTEGER NOT NULL REFERENCES doc_source (id) ON DELETE CASCADE,
  target_raw TEXT NOT NULL,
  target_resolved_path TEXT,
  UNIQUE (from_doc_id, target_raw)
);

-- ---------------------------------------------------------------------------
-- FTS5 search over imported docs (rebuilt on sync for simplicity)
-- ---------------------------------------------------------------------------

CREATE VIRTUAL TABLE IF NOT EXISTS doc_search USING fts5 (
  rel_path UNINDEXED,
  title,
  body,
  tokenize = 'porter unicode61'
);

-- ---------------------------------------------------------------------------
-- Registry: orchestration presets, components, gates, workflow capabilities
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS registry_entity (
  id INTEGER PRIMARY KEY,
  entity_type TEXT NOT NULL,
  slug TEXT NOT NULL,
  display_name TEXT,
  summary TEXT,
  spec_json TEXT,
  primary_doc_path TEXT,
  UNIQUE (entity_type, slug)
);

CREATE INDEX IF NOT EXISTS idx_registry_type ON registry_entity (entity_type);

CREATE TABLE IF NOT EXISTS registry_relation (
  id INTEGER PRIMARY KEY,
  from_entity_id INTEGER NOT NULL REFERENCES registry_entity (id) ON DELETE CASCADE,
  to_entity_id INTEGER NOT NULL REFERENCES registry_entity (id) ON DELETE CASCADE,
  relation_type TEXT NOT NULL,
  meta_json TEXT,
  UNIQUE (from_entity_id, to_entity_id, relation_type)
);

-- ---------------------------------------------------------------------------
-- Runtime: orchestration / execution runs, steps, events, assets
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS execution_run (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  status TEXT NOT NULL,
  orchestration_slug TEXT,
  parent_run_id TEXT REFERENCES execution_run (id) ON DELETE SET NULL,
  git_revision TEXT,
  config_json TEXT NOT NULL,
  environment_json TEXT,
  notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_execution_run_status ON execution_run (status);
CREATE INDEX IF NOT EXISTS idx_execution_run_created ON execution_run (created_at);

CREATE TABLE IF NOT EXISTS execution_step (
  id INTEGER PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES execution_run (id) ON DELETE CASCADE,
  step_order INTEGER NOT NULL,
  stage_slug TEXT REFERENCES pipeline_stage (slug),
  state TEXT NOT NULL,
  started_at TEXT,
  ended_at TEXT,
  error_text TEXT,
  metrics_json TEXT,
  UNIQUE (run_id, step_order)
);

CREATE INDEX IF NOT EXISTS idx_execution_step_run ON execution_step (run_id);

CREATE TABLE IF NOT EXISTS run_event (
  id INTEGER PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES execution_run (id) ON DELETE CASCADE,
  ts TEXT NOT NULL DEFAULT (datetime('now')),
  severity TEXT NOT NULL,
  kind TEXT NOT NULL,
  message TEXT,
  payload_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_run_event_run_ts ON run_event (run_id, ts);

-- Binary or large files stay on disk/object store; DB holds pointers + hashes.
CREATE TABLE IF NOT EXISTS asset (
  id TEXT PRIMARY KEY,
  run_id TEXT REFERENCES execution_run (id) ON DELETE SET NULL,
  interview_id TEXT,
  kind TEXT NOT NULL,
  storage_uri TEXT NOT NULL,
  sha256 TEXT,
  byte_length INTEGER,
  mime_type TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  meta_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_asset_run ON asset (run_id);
CREATE INDEX IF NOT EXISTS idx_asset_interview ON asset (interview_id);
CREATE INDEX IF NOT EXISTS idx_asset_sha ON asset (sha256);

-- ---------------------------------------------------------------------------
-- Domain objects (interview → transcript → segments → EDL) per cross-cutting spec
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS interview (
  id TEXT PRIMARY KEY,
  title TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  meta_json TEXT
);

CREATE TABLE IF NOT EXISTS transcript_revision (
  id TEXT PRIMARY KEY,
  interview_id TEXT NOT NULL REFERENCES interview (id) ON DELETE CASCADE,
  revision_label TEXT,
  provider TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  meta_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_transcript_interview ON transcript_revision (interview_id);

-- Segment record mirrors docs/cross-cutting/segment-schema.md
CREATE TABLE IF NOT EXISTS segment (
  segment_id TEXT NOT NULL,
  interview_id TEXT NOT NULL REFERENCES interview (id) ON DELETE CASCADE,
  transcript_revision_id TEXT REFERENCES transcript_revision (id) ON DELETE SET NULL,
  t_start_ms INTEGER NOT NULL,
  t_end_ms INTEGER NOT NULL,
  text TEXT,
  scores_json TEXT,
  flags_json TEXT,
  mutex_group_id TEXT,
  provenance_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (interview_id, segment_id)
);

CREATE INDEX IF NOT EXISTS idx_segment_time ON segment (interview_id, t_start_ms);

CREATE TABLE IF NOT EXISTS edl_clip (
  id INTEGER PRIMARY KEY,
  run_id TEXT REFERENCES execution_run (id) ON DELETE CASCADE,
  order_index INTEGER NOT NULL,
  segment_id TEXT,
  interview_id TEXT REFERENCES interview (id) ON DELETE SET NULL,
  file_uri TEXT,
  in_ms INTEGER,
  out_ms INTEGER,
  meta_json TEXT,
  UNIQUE (run_id, order_index)
);

CREATE INDEX IF NOT EXISTS idx_edl_run ON edl_clip (run_id);

-- Human control plane (approve / force / gates) — optional structured log
CREATE TABLE IF NOT EXISTS human_decision (
  id INTEGER PRIMARY KEY,
  interview_id TEXT REFERENCES interview (id) ON DELETE CASCADE,
  segment_id TEXT,
  run_id TEXT REFERENCES execution_run (id) ON DELETE SET NULL,
  decided_at TEXT NOT NULL DEFAULT (datetime('now')),
  action TEXT NOT NULL,
  actor TEXT,
  payload_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_human_interview ON human_decision (interview_id);
