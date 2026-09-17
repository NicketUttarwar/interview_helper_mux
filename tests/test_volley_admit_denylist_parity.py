"""Admit denylist ↔ volley_packet_lint parity (ownership telemetry must not LLM-pack)."""

from __future__ import annotations

from interview_mux.volley_packet_lint import (
    _FORBIDDEN_EXACT_KEYS,
    strip_forbidden_metadata,
)


def test_admit_denied_keys_in_volley_exact_set() -> None:
    denied = {"exists", "stage_done", "run_meta", "path_ok", "file_exists"}
    assert denied <= _FORBIDDEN_EXACT_KEYS


def test_strip_forbidden_removes_ownership_telemetry() -> None:
    cleaned = strip_forbidden_metadata(
        {
            "exists": True,
            "stage_done": True,
            "run_meta": {},
            "path_ok": True,
            "file_exists": True,
            "exists_on_disk": True,
            "authority_denied": "leak",
            "tape": {"words": ["ok"]},
        }
    )
    for bad in (
        "exists",
        "stage_done",
        "run_meta",
        "path_ok",
        "file_exists",
        "exists_on_disk",
        "authority_denied",
    ):
        assert bad not in cleaned
    assert cleaned.get("tape") == {"words": ["ok"]}
