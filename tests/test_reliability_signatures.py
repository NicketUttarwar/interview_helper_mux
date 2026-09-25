"""Signature fixtures inspired by exec_1770 / exec_1771 failure modes."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.delivery_recovery import (
    ensure_mmaudio_qa_before_mix,
    suggest_delivery_resume,
)
from interview_mux.order_hash import bump_order_lock, copy_order_lock, order_locks_match
from interview_mux.stage_resilience import escalate_stage_failure, resolve_escalation


def _ctx(tmp_path: Path, name: str = "sig"):
    from interview_mux.run_context import RunContext

    run_dir = tmp_path / name
    run_dir.mkdir()
    (run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    ctx = RunContext.__new__(RunContext)
    ctx.run_dir = run_dir
    ctx.run_id = name

    def final_path(*parts: str) -> Path:
        return run_dir.joinpath(*parts)

    def artifact_exists(rel: str) -> bool:
        return (run_dir / rel).is_file()

    def read_json(rel: str):
        return json.loads((run_dir / rel).read_text(encoding="utf-8"))

    def is_done(sid: str) -> bool:
        return (run_dir / ".stage_done" / sid).is_file()

    def log(*_a, **_k):
        return None

    ctx.final_path = final_path  # type: ignore[method-assign]
    ctx.artifact_exists = artifact_exists  # type: ignore[method-assign]
    ctx.read_json = read_json  # type: ignore[method-assign]
    ctx.is_done = is_done  # type: ignore[method-assign]
    ctx.log = log  # type: ignore[method-assign]
    return ctx


def test_signature_missing_mmaudio_qa_restored(tmp_path: Path):
    """exec_1771-style: missing sound_design/mmaudio_qa.json before mix."""
    ctx = _ctx(tmp_path, "sig_mmaudio")
    assert ensure_mmaudio_qa_before_mix(ctx)["ok"] is False
    arch = ctx.run_dir / ".archived" / "ts1" / "sound_design"
    arch.mkdir(parents=True)
    (arch / "mmaudio_qa.json").write_text('{"passed": true}', encoding="utf-8")
    state = ensure_mmaudio_qa_before_mix(ctx)
    assert state["ok"] is True
    assert state.get("restored") is True


def test_signature_edl_order_drift_selection_leads(tmp_path: Path):
    """Selection lock wins; EDL must copy lock rather than rewrite selection."""
    sel = bump_order_lock(
        {"ordered_segment_ids": ["seg_010", "seg_002"]},
        source="full_master_ranking",
    )
    edl = copy_order_lock(
        sel,
        {"ordered_segment_ids": ["seg_010", "seg_002"], "clips": []},
    )
    assert order_locks_match(sel, edl)


def test_signature_assembly_present_skips_musicgen_replay(tmp_path: Path):
    ctx = _ctx(tmp_path, "sig_resume")
    master = ctx.run_dir / "master"
    master.mkdir()
    (master / "edl.json").write_text("{}", encoding="utf-8")
    (master / "assembly.wav").write_bytes(b"asm" * 100)
    assert suggest_delivery_resume(ctx) in {
        "junction_snip_qa",
        "topic_coverage_audit",
        "edl_narrative_audit",
        "mix",
    }


def test_signature_pmq_escalation_not_auto_waive(tmp_path: Path):
    ctx = _ctx(tmp_path, "sig_pmq")
    doc = escalate_stage_failure(
        ctx,
        "master_finalize",
        failed_invariant="post_master_quality:no_critical_junction_residuals",
    )
    assert doc["quality_first"] is True
    ids = {o["id"] for o in doc["options"]}
    assert "force_publish" not in ids
    resolved = resolve_escalation(ctx, "master_finalize", chosen_option="retry_stage")
    assert resolved["chosen_option"] == "retry_stage"
