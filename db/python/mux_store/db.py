from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _package_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables, seed backbone stages, record migration version."""
    root = _package_dir()
    schema_path = root / "schema.sql"
    seed_path = root / "seed_pipeline_stages.sql"
    if not schema_path.is_file():
        raise FileNotFoundError(f"Missing schema: {schema_path}")
    with schema_path.open("r", encoding="utf-8") as f:
        conn.executescript(f.read())
    if seed_path.is_file():
        with seed_path.open("r", encoding="utf-8") as f:
            conn.executescript(f.read())
    cur = conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = 1")
    if cur.fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (1, 'initial_mux_store')"
        )
    conn.commit()
