"""Gap packet richness, last-good merge, and JSON bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.gap_packet_guard import (
    assert_gap_packet_richness,
    merge_gap_bootstrap_keys,
    merge_last_volley_input,
    persist_last_volley_input,
)
from interview_mux.run_context import RunContext
from interview_mux.volley_packet_lint import lint_llm_user_payload
from run_fixtures import init_run_meta_for_test, patch_executions_root


def test_assert_gap_packet_richness_rejects_empty_segments() -> None:
    payload = {
        "content_brief": {"thesis": "A guest traces how a snack brand grew from a farm."},
        "segments": [],
    }
    lint_llm_user_payload(payload)
    with pytest.raises(ValueError, match="segments"):
        assert_gap_packet_richness("missing_framing", payload)


def test_assert_gap_packet_richness_accepts_manifest_dict_segments() -> None:
    """Host missing_framing payload uses compact_manifest_for_volley (dict, not list)."""
    payload = {
        "content_brief": {"thesis": "A guest traces how a snack brand grew from a farm."},
        "segments": {
            "segments": [{"segment_id": "seg_001", "text": "Native beat from tape."}],
        },
    }
    assert_gap_packet_richness("missing_framing", payload)


def test_assert_gap_packet_richness_rejects_empty_manifest_dict() -> None:
    payload = {
        "content_brief": {"thesis": "A guest traces how a snack brand grew from a farm."},
        "segments": {"segments": []},
    }
    with pytest.raises(ValueError, match="segments"):
        assert_gap_packet_richness("missing_framing", payload)


def test_assert_gap_packet_richness_compose_requires_evals() -> None:
    payload = {
        "content_brief": {"thesis": "A guest traces how a snack brand grew from a farm."},
        "segments": [{"segment_id": "seg_001", "text": "Native beat."}],
        "gap_evaluations": {"evaluations": []},
        "ordered_segment_ids": ["seg_001"],
    }
    with pytest.raises(ValueError, match="gap_evaluations"):
        assert_gap_packet_richness("gap_framing_compose", payload)


def test_merge_gap_bootstrap_keys_json_merges_not_prepend() -> None:
    host = {"segments": [], "other": 1}
    facts = {
        "segments": [{"segment_id": "seg_001"}],
        "content_brief": {"thesis": "Grown from a farm into a national snack brand."},
    }
    merge_gap_bootstrap_keys(host, facts)
    assert host["segments"][0]["segment_id"] == "seg_001"
    assert host["other"] == 1
    assert "thesis" in host["content_brief"]


def test_last_volley_persist_and_reuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_gap_packet", create=True)
    init_run_meta_for_test(ctx)
    good = {
        "segments": [{"segment_id": "seg_001", "text": "Native beat from tape."}],
        "content_brief": {"thesis": "A guest traces how a snack brand grew from a farm."},
    }
    persist_last_volley_input(ctx, "missing_framing", {**good, "exists": True, "run_meta": {}})
    hollow = {"segments": [], "content_brief": {}}
    merged = merge_last_volley_input(ctx, "missing_framing", hollow)
    assert merged["segments"][0]["segment_id"] == "seg_001"
    assert "thesis" in merged["content_brief"]
    stored = ctx.read_json("understanding/stage_runs/missing_framing/last_volley_input.json")
    assert "exists" not in stored
    assert "run_meta" not in stored
