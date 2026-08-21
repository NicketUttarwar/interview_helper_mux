"""Fail-closed gap-stage packets: required keys, last-good volley reuse, JSON merge."""

from __future__ import annotations

import json
from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.volley_packet_lint import strip_forbidden_metadata

GAP_PACKET_STAGES = frozenset({"missing_framing", "gap_framing_compose"})

_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "missing_framing": ("segments", "content_brief"),
    "gap_framing_compose": (
        "segments",
        "content_brief",
        "gap_evaluations",
        "ordered_segment_ids",
    ),
}


def last_volley_rel(stage_key: str) -> str:
    return f"understanding/stage_runs/{stage_key}/last_volley_input.json"


def _key_empty(key: str, value: Any) -> bool:
    if key == "segments":
        # Host gap payloads use compacted manifest dicts ({"segments": [...]});
        # packer bootstrap may also inject a bare list of rows.
        if isinstance(value, list):
            return not value
        if isinstance(value, dict):
            rows = value.get("segments")
            return not isinstance(rows, list) or not rows
        return True
    if key == "content_brief":
        return not isinstance(value, dict) or not value
    if key == "gap_evaluations":
        if isinstance(value, dict):
            return not (value.get("evaluations") or [])
        return not value
    if key == "ordered_segment_ids":
        return not isinstance(value, list) or not value
    if value is None:
        return True
    if isinstance(value, (list, dict, str)):
        return not value
    return False


def merge_gap_bootstrap_keys(host: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    """Copy missing required keys from packed facts. Dict merge, never string prepend."""
    out = host
    for key, src in facts.items():
        if src is None:
            continue
        if key not in out or _key_empty(key, out.get(key)):
            out[key] = src
        elif isinstance(out.get(key), dict) and isinstance(src, dict):
            merged = dict(src)
            merged.update(out[key])
            out[key] = merged
    return out


def persist_last_volley_input(ctx: RunContext, stage_key: str, payload: dict[str, Any]) -> None:
    cleaned = strip_forbidden_metadata(payload)
    if not isinstance(cleaned, dict):
        return
    ctx.write_json(last_volley_rel(stage_key), cleaned, skip_handoff=True)


def merge_last_volley_input(
    ctx: RunContext, stage_key: str, payload: dict[str, Any]
) -> dict[str, Any]:
    rel = last_volley_rel(stage_key)
    if not ctx.artifact_exists(rel):
        return payload
    try:
        prior = ctx.read_json(rel)
    except Exception:
        return payload
    if not isinstance(prior, dict):
        return payload
    prior = strip_forbidden_metadata(prior)
    if not isinstance(prior, dict):
        return payload
    out = dict(payload)
    for key in _REQUIRED_KEYS.get(stage_key, ()):
        if _key_empty(key, out.get(key)) and not _key_empty(key, prior.get(key)):
            out[key] = prior[key]
    return out


def assert_gap_packet_richness(stage_key: str, payload: dict[str, Any]) -> None:
    required = _REQUIRED_KEYS.get(stage_key)
    if not required:
        return
    missing = [key for key in required if _key_empty(key, payload.get(key))]
    if missing:
        raise ValueError(
            f"{stage_key} packet missing required keys: {', '.join(missing)}"
        )


def host_packet_from_user_text(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw.startswith("{"):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
