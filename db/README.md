# Canonical SQLite store (`mux_store`)

This repository’s **single logical database** is a **SQLite file** created from `schema.sql` and fed by the Python package under `db/python/mux_store/`. It holds:

- **Specs and ideas**: every Markdown file under `docs/` plus the repo-root `README.md` (full text, front matter JSON, link graph, `depends_on` edges, FTS5 search).
- **Pipeline vocabulary**: seeded `pipeline_stage` rows for the backbone DAG and the human control plane.
- **Runtime**: execution runs, ordered steps, structured events, on-disk **asset** pointers (hashes, URIs, metadata), interviews / transcript revisions / **segments** (aligned with `docs/cross-cutting/segment-schema.md`), EDL clips, and human decisions.

Binary media and large artifacts are **not** stored as BLOBs in SQLite; they live on disk or object storage, with this database holding **URIs, checksums, and JSON metadata** (`asset` table).

## Requirements

- **Python 3.12+** (same as repo `.venv`; see [SETUP.md](../SETUP.md)).
- **SQLite 3** with [FTS5](https://www.sqlite.org/fts5.html) enabled (default in modern builds).

No third-party packages are required for `mux_store` alone.

If orchestration code calls **AWS** (S3 asset URIs, Transcribe, etc.), use the same repo-wide secrets file as the other integrations: `config/secrets/secrets.env` parsed via `mux_secrets.load_repo_config()` (see repository `config/README.md`).

## Layout

| Path | Role |
|------|------|
| `db/schema.sql` | DDL: tables, indexes, FTS5 `doc_search`, foreign keys |
| `db/seed_pipeline_stages.sql` | Backbone `pipeline_stage` inserts |
| `db/python/mux_store/` | `connect`, `init_db`, `sync_markdown_tree`, runtime helpers |
| `tools/sync_to_sqlite.py` | CLI: create DB + sync Markdown |
| `config/app.defaults.json` | Default `database_path` for tools (committed) |
| `data/interview_mux.sqlite` | Typical DB location (gitignored); directory keeps `.gitkeep` |

## Quick start

From the repository root:

```bash
python3 tools/sync_to_sqlite.py
```

Optional arguments:

```bash
python3 tools/sync_to_sqlite.py --db /path/to/custom.sqlite --repo /path/to/interview_helper_mux
```

## Embedding in orchestration code

Install the repo in your venv (`pip install -r requirements.txt` from the repository root), then:

```python
from pathlib import Path
from mux_store import (
    connect,
    create_run,
    append_event,
    default_sqlite_path,
    init_db,
    register_asset,
    sync_markdown_tree,
)

repo = Path("/path/to/interview_helper_mux")
conn = connect(default_sqlite_path(repo))
init_db(conn)
sync_markdown_tree(conn, repo)

run_id = create_run(conn, status="running", orchestration_slug="A", config={"budget_s": 600})
append_event(conn, run_id, kind="ingest", message="normalized wav", payload={"uri": "file:///…"})
register_asset(conn, kind="audio/wav", storage_uri="file:///tmp/normalized.wav", run_id=run_id, sha256="…")
```

## Main tables (conceptual map)

- **`doc_source` / `doc_dependency` / `doc_outbound_link` / `doc_search`** — documentation corpus and graph; FTS for full-text search.
- **`pipeline_stage`** — ordered backbone stages (see `docs/execution/orchestration-component-map.md`).
- **`registry_entity` / `registry_relation`** — optional catalog of named components, presets, gates (populate from your implementation).
- **`execution_run` / `execution_step` / `run_event`** — durable run ledger for orchestrators (`execution_run.runtime_context_json` holds optional non-secret run context).
- **`execution_kv`** — small JSON key/value scratch space for local execution (never store secrets here).
- **`asset`** — pointers to waveforms, spectrograms, manifests, checkpoints, exports.
- **`interview` / `transcript_revision` / `segment`** — domain objects for scoring, review, and mux.
- **`edl_clip`** — ordered timeline references (segment id and/or explicit file + in/out).
- **`human_decision`** — structured control-plane actions (approve, force include, gate resolution).

## Schema evolution

Bump `schema_migrations` with new numbered migrations when you change `schema.sql` in a breaking way; keep additive changes idempotent with `IF NOT EXISTS` / `INSERT OR IGNORE` where possible.
