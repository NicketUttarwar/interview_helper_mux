from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Iterable

from mux_store.front_matter import front_matter_json, split_front_matter

# [text](target) and bare docs/...md paths
_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_BARE_MD = re.compile(r"(?:^|[\s(])(docs/[^\s)]+\.md)")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _domain_for_rel(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) >= 2 and parts[0] == "docs":
        return parts[1]
    return "root"


def _title_from_body(body: str, fallback: str) -> str:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _iter_markdown_files(docs_root: Path) -> Iterable[Path]:
    yield from sorted(docs_root.rglob("*.md"))


def _resolve_link_target(raw: str, current_file: Path, repo_root: Path) -> str | None:
    target = raw.split("#", 1)[0].strip()
    if target.startswith(("http://", "https://", "mailto:")):
        return None
    if not target:
        return None
    base = current_file.parent
    candidate = (base / target).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        return None
    if candidate.is_file():
        return str(candidate.relative_to(repo_root))
    return None


def _extract_outbound_links(body: str, current_rel: str, repo_root: Path) -> list[str]:
    current_file = repo_root / current_rel
    out: list[str] = []
    for m in _MD_LINK.finditer(body):
        raw = m.group(1).strip()
        out.append(raw)
    for m in _BARE_MD.finditer(body):
        out.append(m.group(1))
    return out


def sync_markdown_tree(conn: sqlite3.Connection, repo_root: Path, docs_rel: str = "docs") -> int:
    """Upsert all *.md under docs/ plus repo-root README.md; refresh FTS; rebuild edges."""
    docs_root = (repo_root / docs_rel).resolve()
    if not docs_root.is_dir():
        raise FileNotFoundError(docs_root)

    slug_to_id: dict[str, int] = {}
    path_to_id: dict[str, int] = {}

    count = 0
    root_readme = repo_root / "README.md"
    if root_readme.is_file():
        paths: list[Path] = [root_readme, *_iter_markdown_files(docs_root)]
    else:
        paths = list(_iter_markdown_files(docs_root))

    for path in paths:
        rel = str(path.relative_to(repo_root))
        raw = path.read_text(encoding="utf-8", errors="replace")
        meta, body = split_front_matter(raw)
        title = meta.get("title") if isinstance(meta.get("title"), str) else None
        if not title:
            title = _title_from_body(body, path.stem.replace("-", " ").title())
        domain = "repo_root" if rel == "README.md" else _domain_for_rel(rel)
        doc_slug = meta.get("id") if isinstance(meta.get("id"), str) else None
        tier = meta.get("tier") if isinstance(meta.get("tier"), str) else None
        status = meta.get("status") if isinstance(meta.get("status"), str) else None
        fm_json = front_matter_json(meta)
        digest = _sha256(raw)
        mtime = path.stat().st_mtime

        conn.execute(
            """
            INSERT INTO doc_source (
              rel_path, domain, title, doc_slug, tier, status,
              front_matter_json, body_markdown, content_sha256, file_mtime_unix
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rel_path) DO UPDATE SET
              domain = excluded.domain,
              title = excluded.title,
              doc_slug = excluded.doc_slug,
              tier = excluded.tier,
              status = excluded.status,
              front_matter_json = excluded.front_matter_json,
              body_markdown = excluded.body_markdown,
              content_sha256 = excluded.content_sha256,
              file_mtime_unix = excluded.file_mtime_unix,
              imported_at = datetime('now')
            """,
            (rel, domain, title, doc_slug, tier, status, fm_json, body, digest, mtime),
        )
        row = conn.execute("SELECT id FROM doc_source WHERE rel_path = ?", (rel,)).fetchone()
        doc_id = int(row[0])
        path_to_id[rel] = doc_id
        if doc_slug:
            slug_to_id[doc_slug] = doc_id
        count += 1

    conn.execute("DELETE FROM doc_dependency")
    conn.execute("DELETE FROM doc_outbound_link")
    conn.execute("DELETE FROM doc_search")

    for rel, doc_id in path_to_id.items():
        row = conn.execute(
            "SELECT body_markdown, front_matter_json FROM doc_source WHERE id = ?",
            (doc_id,),
        ).fetchone()
        body = row[0]
        meta = json.loads(row[1])
        depends = meta.get("depends_on")
        if isinstance(depends, list):
            for slug in depends:
                if not isinstance(slug, str):
                    continue
                to_id = slug_to_id.get(slug)
                conn.execute(
                    "INSERT INTO doc_dependency (from_doc_id, depends_on_slug, to_doc_id) VALUES (?, ?, ?)",
                    (doc_id, slug, to_id),
                )

        for raw in _extract_outbound_links(body, rel, repo_root):
            resolved = _resolve_link_target(raw, repo_root / rel, repo_root)
            conn.execute(
                """
                INSERT INTO doc_outbound_link (from_doc_id, target_raw, target_resolved_path)
                VALUES (?, ?, ?)
                ON CONFLICT(from_doc_id, target_raw) DO NOTHING
                """,
                (doc_id, raw, resolved),
            )

        title_row = conn.execute("SELECT title FROM doc_source WHERE id = ?", (doc_id,)).fetchone()
        title = title_row[0] or ""
        conn.execute(
            "INSERT INTO doc_search (rel_path, title, body) VALUES (?, ?, ?)",
            (rel, title, body),
        )

    conn.commit()
    return count
