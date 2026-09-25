"""Tests for refinement CFI, ledger, gate, and flow integrity."""

from __future__ import annotations

import json

import pytest

from interview_mux.refinement_agenda import run_refinement_agenda
from interview_mux.refinement_catalog import is_blacklisted, is_whitelisted
from interview_mux.refinement_flow_integrity import (
    FINAL_REL,
    ensure_gap_report_authoritative,
    g1_reachable,
    skip_copy_draft_to_final,
)
from interview_mux.refinement_gate import decide_pass
from interview_mux.refinement_identity import (
    assert_acyclic_refines,
    assert_unique_registry,
    cfi_for_pass,
    register_builtin_cfis,
)
from interview_mux.refinement_ledger import can_run_refinement, load_ledger, record_call
from interview_mux.run_context import RunContext
from interview_mux.refinement_accept import accept_gap_recompose
from interview_mux.refinement_champion import load_champion
from interview_mux.refinement_succession import is_unlocked, mutex_blocked
from interview_mux.refinement_gate import compute_input_hash
from run_fixtures import patch_executions_root, mark_done_raw, write_fixture_json


def _plant_snapshot(ctx: RunContext, pass_id: str, rel_paths: list[str]) -> str:
    digest = compute_input_hash(ctx, rel_paths)
    write_fixture_json(
        ctx,
        f"understanding/refinement_snapshots/{pass_id}/meta.json",
        {
            "paths": [{"rel": rel, "present": ctx.artifact_exists(rel)} for rel in rel_paths],
            "input_hash": digest,
        },
    )
    return digest


def _raw_json(ctx: RunContext, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def ctx(tmp_path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    # Isolate each test under tmp_path — a plain env var does not affect
    # RunContext's executions_root resolution (it reads merged_config()).
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_refinement_test", create=True)
    return run


def test_cfi_registry_unique() -> None:
    register_builtin_cfis()
    assert_unique_registry()
    assert_acyclic_refines()
    assert cfi_for_pass("gap_framing_recompose") is not None


def test_blacklist_wins() -> None:
    assert is_blacklisted(stage_id="ingest")
    assert not is_whitelisted("ingest")
    assert is_whitelisted("gap_framing_recompose")


def test_ledger_refinement_cap(ctx: RunContext) -> None:
    cfi = cfi_for_pass("gap_framing_recompose")
    assert cfi is not None
    # Ensure clean ledger for this CFI
    from interview_mux.refinement_ledger import LEDGER_REL, save_ledger

    save_ledger(
        ctx,
        {
            "run_id": ctx.run_id,
            "schema_version": 1,
            "calls": [],
            "counts_by_cfi": {},
            "order_of_refinement_pass_ids": [],
        },
    )
    assert can_run_refinement(ctx, cfi.cfi_id)
    record_call(
        ctx,
        cfi_id=cfi.cfi_id,
        human_key=cfi.human_key,
        stage_id="gap_framing_recompose",
        pass_id="gap_framing_recompose",
        pass_index=2,
        kind="refinement",
        outcome="ok",
    )
    assert not can_run_refinement(ctx, cfi.cfi_id)
    with pytest.raises(RuntimeError):
        record_call(
            ctx,
            cfi_id=cfi.cfi_id,
            human_key=cfi.human_key,
            stage_id="gap_framing_recompose",
            pass_id="gap_framing_recompose",
            pass_index=2,
            kind="refinement",
            outcome="ok",
        )
    doc = load_ledger(ctx)
    assert doc["counts_by_cfi"][cfi.cfi_id]["refinement"] == 1
    _ = LEDGER_REL


def test_skip_copy_and_g1_reachable(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.draft.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_1",
                    "text": "Hello",
                    "targets_segment_id": "seg_1",
                    "gap_type": "missing_question",
                    "placement": "before",
                    "delivery": "synthesize",
                }
            ]
        },
    )
    skip_copy_draft_to_final(ctx, reason="simple_tape")
    assert ctx.artifact_exists(FINAL_REL)
    final = ctx.read_json(FINAL_REL)
    assert len(final.get("interviewer_lines") or []) == 1
    assert g1_reachable(ctx)
    ensure_gap_report_authoritative(ctx)


def test_decide_pass_blacklist_or_simple(ctx: RunContext) -> None:
    d = decide_pass(ctx, "ingest")
    assert d["status"] == "skip"


# ---------------------------------------------------------------------------
# Succession — slim Pass-2 (legacy unlocks opt-in)
# ---------------------------------------------------------------------------


def test_slim_pass2_active_passes_unlocked(ctx: RunContext) -> None:
    assert is_unlocked(ctx, "gap_framing_recompose")
    assert is_unlocked(ctx, "selection_framing_apply")


def test_mutex_inactive_without_legacy_rules(ctx: RunContext) -> None:
    mark_done_raw(ctx, "narrative_arc_refine")
    # Slim defaults have empty mutex — legacy refine stubs are not gated.
    assert not mutex_blocked(ctx, "ranking_refine")


def test_legacy_succession_injectable(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.refinement_succession.refinement_cfg",
        lambda: {
            "succession": {
                "unlocks": [
                    {
                        "after_accept_or_skip_copy": "gap_framing_recompose",
                        "unlock": "transitions_refine",
                    }
                ],
                "mutex": [
                    {
                        "passes": ["narrative_arc_refine", "ranking_refine"],
                        "when": "both_would_reorder",
                    }
                ],
                "priority": ["gap_framing_recompose", "selection_framing_apply"],
            }
        },
    )
    assert not is_unlocked(ctx, "transitions_refine")
    mark_done_raw(ctx, "gap_framing_recompose")
    assert is_unlocked(ctx, "transitions_refine")
    assert not mutex_blocked(ctx, "ranking_refine")
    mark_done_raw(ctx, "narrative_arc_refine")
    assert mutex_blocked(ctx, "ranking_refine")


# ---------------------------------------------------------------------------
# L1 gate — input-hash skip (no new evidence)
# ---------------------------------------------------------------------------


def test_gate_skips_on_unchanged_input_hash(ctx: RunContext) -> None:
    write_fixture_json(ctx, "understanding/gap_report.draft.json", {"interviewer_lines": []})
    write_fixture_json(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_1"]})
    req = ["understanding/gap_report.draft.json", "master/selection.json"]

    first = decide_pass(ctx, "gap_framing_recompose")
    assert first["status"] == "activate"

    # Simulate a completed refinement run: freeze inputs, write the final
    # gap_report, and mark the stage done — matching what
    # refinement_passes.run_gap_framing_recompose does on success.
    _plant_snapshot(ctx, "gap_framing_recompose", req)
    write_fixture_json(
        ctx,
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        stage_key="gap_framing_compose",
    )
    mark_done_raw(ctx, "gap_framing_recompose")

    second = decide_pass(ctx, "gap_framing_recompose")
    assert second["status"] == "skip"
    assert second["reason_code"] == "no_new_evidence"
    assert second["gate"] == "input_hash"


# ---------------------------------------------------------------------------
# Champion accept — noop guard + promote
# ---------------------------------------------------------------------------


def _gap_line(line_id: str, text: str, **overrides: object) -> dict[str, object]:
    line: dict[str, object] = {
        "line_id": line_id,
        "text": text,
        "targets_segment_id": "seg_1",
        "gap_type": "missing_question",
        "placement": "before",
        "delivery": "synthesize",
    }
    line.update(overrides)
    return line


def test_accept_gap_recompose_noop_when_unchanged(ctx: RunContext) -> None:
    draft = {"interviewer_lines": [_gap_line("vo_1", "Hello")]}
    write_fixture_json(ctx, "understanding/gap_report.draft.json", draft)

    result = accept_gap_recompose(ctx, dict(draft))
    assert result["accepted"] is False
    assert result["reason_code"] == "noop"
    final = ctx.read_json(FINAL_REL)
    assert final.get("interviewer_lines") == draft["interviewer_lines"]
    assert isinstance(final.get("_meta"), dict)  # sanitize stamp on write


def test_accept_gap_recompose_promotes_champion_on_improvement(ctx: RunContext) -> None:
    draft = {"interviewer_lines": [_gap_line("vo_1", "Hello")]}
    write_fixture_json(ctx, "understanding/gap_report.draft.json", draft)
    write_fixture_json(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_1"]})
    orig_write = ctx.write_json

    def _gap_via_compose(rel, data, **kwargs):
        if rel == "understanding/gap_report.json":
            kwargs.setdefault("stage_key", "gap_framing_compose")
        if str(rel).startswith("understanding/refinement_"):
            return write_fixture_json(ctx, rel, data)
        return orig_write(rel, data, **kwargs)

    ctx.write_json = _gap_via_compose  # type: ignore[method-assign]
    assert load_champion(ctx, "gap_vo") is None

    candidate = {
        "interviewer_lines": [
            _gap_line("vo_1", "Hello"),
            _gap_line(
                "vo_2",
                "Welcome back to the show",
                line_category="episode_preface",
            ),
        ]
    }
    result = accept_gap_recompose(ctx, candidate)
    assert result["accepted"] is True
    assert result["reason_code"] == "accepted"
    final = ctx.read_json(FINAL_REL)
    assert final.get("interviewer_lines") == candidate["interviewer_lines"]
    assert isinstance(final.get("_meta"), dict)

    champion = load_champion(ctx, "gap_vo")
    assert champion is not None
    assert champion["source"] == "gap_framing_recompose"
    assert champion["score_vector"] == result["candidate_scores"]


def test_confirm_phase_injects_ranking_on_coverage_holes(ctx: RunContext) -> None:
    """RA-B3: confirm opens ranking when coverage holes exist (even simple_tape).

    Explicit ``phase="draft"`` is test-only contrast against confirm injects.
    """
    _raw_json(
        ctx,
        "understanding/source_topology.json",
        {"topology_class": "short_clean", "class": "short_clean"},
    )
    _raw_json(
        ctx,
        "understanding/source_acoustic_profile.json",
        {"duration_sec": 300},
    )
    _raw_json(ctx, "understanding/gap_evaluations.json", {"evaluations": []})
    _raw_json(
        ctx,
        "master/coverage_audit.json",
        {"uncovered_topics": [{"topic": "origin story", "severity": "high"}]},
    )

    draft = run_refinement_agenda(ctx, phase="draft")
    assert "ranking" not in (draft.get("eligible_classes") or [])

    confirm = run_refinement_agenda(ctx, phase="confirm")
    assert "ranking" in (confirm.get("eligible_classes") or [])
    assert confirm.get("phase") == "confirm"
    assert "post_gap_topic_holes_ranking" in (confirm.get("succession_hints") or [])
    assert ctx.is_done("refinement_agenda")


def test_refinement_agenda_blocks_when_gap_unsanitary(ctx: RunContext) -> None:
    """RA-B2: present dirty gap_report refuses agenda (resume sanitize)."""
    prev = getattr(ctx, "_one_writer_raw", False)
    ctx._one_writer_raw = True
    try:
        _raw_json(
            ctx,
            "understanding/gap_report.json",
            {
                "interviewer_lines": [
                    {
                        "line_id": "vo_a",
                        "text": "Hello world enough words here.",
                        "targets_segment_id": "seg_001",
                    }
                ],
                "gaps": "unsanitary",
            },
        )
    finally:
        ctx._one_writer_raw = prev

    with pytest.raises(RuntimeError, match="gap_unsanitary"):
        run_refinement_agenda(ctx, phase="confirm")
    assert not ctx.is_done("refinement_agenda")


def test_gap_framing_recompose_layup_authority_accept_sidecar(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GFR-B4: Full-auto defaults → thin adapter writes accept sidecar (no LLM)."""
    from interview_mux.nugget_layup import PLAN_REL
    from interview_mux.refinement_passes import run_gap_framing_recompose

    monkeypatch.setattr(
        "interview_mux.seat_authority.gate_seat_mutation",
        lambda *_a, **_k: True,
    )
    ordered = ["seg_011", "seg_028"]
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ordered})
    segments = []
    start = 0
    for sid in ordered:
        segments.append(
            {
                "segment_id": sid,
                "speaker_id": "spk_0",
                "speaker_role": "interviewee",
                "type": "interviewee_answer",
                "topic_tags": [],
                "text": f"Native content for {sid} with enough words to stay on air.",
                "start_ms": start,
                "end_ms": start + 9000,
            }
        )
        start += 12_000
    ctx.write_json("segments/manifest.json", {"segments": segments})
    analysis = {
        "target_beat": "The exit negotiation",
        "listener_need_entering_T": "The prior clip ended before the buyer appeared",
        "forward_unlock": "Why the snack pivot decided the price",
    }
    plan = {
        "ordered_segment_ids": ordered,
        "layups": [
            {
                "target_segment_id": "seg_028",
                "line_id": "vo_layup_seg_028",
                "text": (
                    "The employee pool reached shop-floor staff, not just senior "
                    "managers. What did the buyer promise in writing?"
                ),
                "nugget_ids": ["nug_esop"],
                "skip": False,
                "forward_cue_ok": True,
                **analysis,
            }
        ],
    }
    ctx.write_json(PLAN_REL, plan)
    # Prior gap so orientation/publish has a base document.
    ctx.write_json(
        FINAL_REL,
        {
            "interviewer_lines": [],
            "nugget_layup_authority": True,
        },
        skip_handoff=True,
    )

    run_gap_framing_recompose(ctx)

    sidecar = ctx.read_json("understanding/gap_framing_recompose.json")
    assert sidecar.get("accept", {}).get("accepted") is True
    assert sidecar.get("accept", {}).get("reason_code") == "nugget_layup_authority"
    assert ctx.is_done("gap_framing_recompose")
    gap = ctx.read_json(FINAL_REL)
    assert gap.get("nugget_layup_authority") is True
    assert any(
        isinstance(ln, dict) and ln.get("origin") == "nugget_layup"
        for ln in (gap.get("interviewer_lines") or [])
    )


def test_gap_framing_recompose_retires_legacy_activate(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GFR-B3: without layup authority, activate becomes skip-copy (no filter path)."""
    from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta
    from interview_mux.refinement_flow_integrity import SKIP_COPY_REL
    from interview_mux.refinement_passes import run_gap_framing_recompose

    monkeypatch.setattr(
        "interview_mux.seat_authority.gate_seat_mutation",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "interview_mux.refinement_passes.decide_pass",
        lambda *_a, **_k: {
            "status": "activate",
            "reason_code": "would_have_activated",
            "pass_id": "gap_framing_recompose",
        },
    )
    stamped = stamp_sanitize_meta(
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_keep",
                    "text": "Keep this line through skip-copy.",
                    "targets_segment_id": "seg_001",
                    "origin": "draft",
                }
            ],
            "gaps": [],
        },
        ok=True,
        source="gap_report_sanitize",
        content_keys=["interviewer_lines", "gaps", "opening_orientation"],
    )
    _raw_json(ctx, FINAL_REL, stamped)

    run_gap_framing_recompose(ctx)

    assert ctx.artifact_exists(SKIP_COPY_REL)
    skip = ctx.read_json(SKIP_COPY_REL)
    assert skip.get("reason") == "legacy_activate_retired"
    assert ctx.is_done("gap_framing_recompose")
    gap = ctx.read_json(FINAL_REL)
    assert any(
        isinstance(ln, dict) and ln.get("line_id") == "vo_keep"
        for ln in (gap.get("interviewer_lines") or [])
    )
