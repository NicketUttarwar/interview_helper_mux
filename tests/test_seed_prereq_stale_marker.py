"""A prerequisite with a stale .stage_done is rerun, not trusted (ISSUES 86);
a refused content-brief courtesy write is skipped, not logged as a denial (ISSUES 87)."""

from __future__ import annotations

import json

import pytest
from run_fixtures import isolated_run_ctx, mark_done_raw

from interview_mux.artifact_repairs import propagate_nle_split_segment_refs
from interview_mux.homunculus.agenda import _seed_prereq_needs_run


def test_prereq_marked_done_but_not_seed_complete_is_rerun(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_stale_prereq")
    mark_done_raw(ctx, "full_master_ranking")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete", lambda _c, _s: False
    )
    assert _seed_prereq_needs_run(ctx, "full_master_ranking") is True
    assert not ctx.is_done("full_master_ranking"), "the stale marker must be dropped first"


def test_prereq_that_is_genuinely_complete_is_left_alone(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_complete_prereq")
    mark_done_raw(ctx, "full_master_ranking")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete", lambda _c, _s: True
    )
    assert _seed_prereq_needs_run(ctx, "full_master_ranking") is False
    assert ctx.is_done("full_master_ranking")


def test_prereq_without_marker_is_run(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_unmarked_prereq")
    assert _seed_prereq_needs_run(ctx, "full_master_ranking") is True


def _brief(ctx) -> None:
    path = ctx.final_path("understanding", "content_brief.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"topics": [{"topic_id": "t1", "segment_ids": ["seg_010"]}], "key_claims": []}),
        encoding="utf-8",
    )


def test_denied_brief_remap_is_skipped_without_a_denial(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_brief_denied")
    _brief(ctx)
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *_a, **_k: (False, "not_allow:owner=content_brief_reanchor"),
    )
    monkeypatch.setattr("interview_mux.write_staging.active_stage_id", lambda: "full_master_ranking")
    denials: list[str] = []
    monkeypatch.setattr(
        "interview_mux.artifact_ownership._log_authority_denied",
        lambda _c, exc: denials.append(str(exc)),
    )
    updated = propagate_nle_split_segment_refs(ctx, "seg_010", ["seg_010a", "seg_010b"])
    assert "understanding/content_brief.json" not in updated
    assert denials == []
    doc = json.loads(ctx.final_path("understanding", "content_brief.json").read_text(encoding="utf-8"))
    assert doc["topics"][0]["segment_ids"] == ["seg_010"]


def test_permitted_brief_remap_still_rewrites(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_brief_allowed")
    _brief(ctx)
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted", lambda *_a, **_k: (True, "")
    )
    written: list[dict] = []
    monkeypatch.setattr(
        "interview_mux.shared_path_commit.commit_content_brief_doc",
        lambda _c, doc, **_k: written.append(doc),
    )
    updated = propagate_nle_split_segment_refs(ctx, "seg_010", ["seg_010a", "seg_010b"])
    assert "understanding/content_brief.json" in updated
    assert written and written[0]["topics"][0]["segment_ids"] == ["seg_010a", "seg_010b"]
