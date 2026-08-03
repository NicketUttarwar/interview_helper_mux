"""Episode sequence + V2 title suffix by source_audio_hash."""

from __future__ import annotations

from typing import Any


def allocate_episode_number(sequence: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Return next 1-based episode number and updated sequence dict."""
    next_n = int(sequence.get("next_episode_number") or 1)
    if next_n < 1:
        next_n = 1
    updated = dict(sequence)
    updated["next_episode_number"] = next_n + 1
    return next_n, updated


def episode_folder(episode_number: int) -> str:
    return f"{int(episode_number):04d}"


def load_by_source_hash(catalog: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(catalog, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for key, rows in catalog.items():
        if isinstance(rows, list):
            out[str(key)] = [r for r in rows if isinstance(r, dict)]
    return out


def prior_publish_count(by_hash: dict[str, list[dict[str, Any]]], source_audio_hash: str) -> int:
    return len(by_hash.get(source_audio_hash) or [])


def apply_version_suffix(base_title: str, *, prior_count: int) -> str:
    """First publish: base title. Second: ' V2', third: ' V3', …"""
    title = (base_title or "").strip() or "Untitled Episode"
    attempt = prior_count + 1
    if attempt <= 1:
        return title
    # Strip an existing trailing Vn to avoid V2 V3 stacking on re-title
    import re

    cleaned = re.sub(r"\s+V\d+\s*$", "", title).strip() or title
    return f"{cleaned} V{attempt}"


def record_publish(
    by_hash: dict[str, list[dict[str, Any]]],
    *,
    source_audio_hash: str,
    episode_number: int,
    title: str,
    execution_id: str,
    published_at: str,
    s3_prefix: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    updated = {k: list(v) for k, v in by_hash.items()}
    rows = list(updated.get(source_audio_hash) or [])
    row: dict[str, Any] = {
        "episode_number": episode_number,
        "title": title,
        "execution_id": execution_id,
        "published_at": published_at,
    }
    if s3_prefix:
        row["s3_prefix"] = s3_prefix
    rows.append(row)
    updated[source_audio_hash] = rows
    return updated


def record_execution(
    by_execution: dict[str, Any] | None,
    *,
    execution_id: str,
    episode_number: int,
    title: str,
    source_audio_hash: str,
    published_at: str,
    s3_prefix: str,
) -> dict[str, Any]:
    """Index episode folder by pipeline execution_id for retrieveability."""
    updated = dict(by_execution or {})
    if not execution_id:
        return updated
    updated[execution_id] = {
        "episode_number": episode_number,
        "title": title,
        "source_audio_hash": source_audio_hash,
        "published_at": published_at,
        "s3_prefix": s3_prefix,
    }
    return updated
