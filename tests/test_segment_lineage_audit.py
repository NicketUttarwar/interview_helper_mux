from __future__ import annotations

import json

import pytest

from interview_mux.artifact_repairs import repair_coverage_audit
from interview_mux.artifact_cross_validate import validate_cross_artifacts
from interview_mux.segment_lineage_audit import audit_artifact, audit_run, collect_segment_refs_from_doc
from run_fixtures import isolated_run_ctx, minimal_content_brief, minimal_manifest, minimal_manifest_segment


def test_collect_segment_refs_content_brief() -> None:
    doc = {
        "thesis": "Test thesis",
        "topics": [{"name": "A", "summary": "s", "segment_ids": ["seg_001", "seg_002"]}],
    }
    refs = collect_segment_refs_from_doc("understanding/content_brief.json", doc)
    assert refs == {"seg_001", "seg_002"}


def test_audit_artifact_orphans(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lineage_orphan")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), skip_handoff=True)
    ctx.write_json(
        "understanding/content_brief.json",
        {
            **minimal_content_brief(),
            "topics": [{"name": "T", "summary": "s", "segment_ids": ["seg_orphan"]}],
        },
        skip_handoff=True,
    )
    info = audit_artifact(ctx, "understanding/content_brief.json", universe={"seg_001"})
    assert "seg_orphan" in info["orphans"]


def test_repair_coverage_audit_segment_ids(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "repair_coverage")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001", "seg_002"), skip_handoff=True)
    ctx.write_json("understanding/content_brief.json", minimal_content_brief(), skip_handoff=True)
    doc = {
        "topic_mappings": [
            {"topic": "Topic A", "segment_ids": ["seg_001", "seg_bad"], "covered": True},
        ],
        "claim_mappings": [],
        "coverage_score": 0.5,
    }
    patched, applied = repair_coverage_audit(ctx, doc)
    assert "seg_bad" not in (patched["topic_mappings"][0].get("segment_ids") or [])
    assert "seg_002" in (patched.get("orphan_segment_ids") or [])
    assert applied


def test_post_coverage_audit_checkpoint(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_coverage")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), skip_handoff=True)
    ctx.write_json(
        "master/coverage_audit.json",
        {
            "topic_mappings": [{"topic": "T", "segment_ids": ["seg_999"], "covered": True}],
            "coverage_score": 0.5,
        },
        skip_handoff=True,
    )
    errors = validate_cross_artifacts(ctx, "post_coverage_audit")
    assert any("seg_999" in e for e in errors)


def test_post_episode_structure_checkpoint(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "cv_episode")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"), skip_handoff=True)
    from interview_mux.episode_structure import build_episode_structure

    doc = build_episode_structure(ctx, refresh=False)
    doc["segment_order"] = ["seg_999", "seg_001"]
    path = ctx.path("understanding", "episode_structure.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    errors = validate_cross_artifacts(ctx, "post_episode_structure")
    assert any("seg_999" in e for e in errors)


def test_selection_excluded_ids_are_not_orphans(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Excluded kept-out segments are intentional — not lineage orphans."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "lineage_excl")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest("seg_001", "seg_002", "seg_003"),
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_002"],
            "excluded_segment_ids": [
                {"segment_id": "seg_001", "reason": "cut"},
                {"segment_id": "seg_003", "reason": "cut"},
            ],
            "chapters": [],
        },
        skip_handoff=True,
    )
    report = audit_run(ctx)
    assert not any("orphan segment ref" in f for f in report["hard_failures"])


def test_audit_run_fixture_chain(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    from progression_chain_sanity_helpers import FULL_PROGRESSION_CHAIN, run_progression_chain_sanity

    ctx = isolated_run_ctx(tmp_path, "lineage_chain")
    run_progression_chain_sanity(ctx, chain=list(FULL_PROGRESSION_CHAIN))
    report = audit_run(ctx)
    assert "artifacts" in report
    assert isinstance(report.get("hard_failures"), list)
