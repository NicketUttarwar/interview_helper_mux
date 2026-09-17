"""p15-attempt-memo (§5.3): a driver re-entry stops re-walking the same remaining set.

exec_11871: 148 ``delivery_walk_to_master`` + 63 ``analysis_fill_delivery_prereqs``
re-entries each recomputed ``remaining`` and walked the same stages again — 69 excess
dispatches (``missing_framing`` 22, ``vernacular_segment_sanitize`` 14,
``connector_fuse_pass`` 12, ``speaker_roles`` 11, ``mastering_research_waves`` 10).

The memo may never hide a stage permanently, and it may never touch operator gates
in any of the three postures.
"""

from __future__ import annotations

from pathlib import Path

from interview_mux.automation_run import PARTIAL_MAY_PAUSE_GATES, PARTIAL_MUST_ACT_GATES
from interview_mux.defect_ledger import open_defects
from interview_mux.dispatch_delta import (
    memo_skip,
    progress_token,
    record_attempt,
)
from interview_mux.dispatch_door import door_applies, evaluate_dispatch
from interview_mux.homunculus.ledger import append_ledger
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, mark_done_raw

STAGE = "vernacular_segment_sanitize"


def _ctx(tmp_path: Path, name: str, **meta: object) -> RunContext:
    ctx = isolated_run_ctx(tmp_path, name)
    base = {
        "homunculus_version": "0.2.0",
        "homunculus_kind": "homunculus",
        "homunculus_control_plane": "deterministic",
        "run_mode": "full-auto",
        "full_auto": True,
    }
    base.update(meta)
    ctx.write_json("run_meta.json", base, skip_handoff=True)
    return ctx


def test_unchanged_stage_is_not_re_offered_on_the_next_re_entry(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "memo_reentry")
    record_attempt(ctx, STAGE, outcome="failed", source="delivery_walk_to_master")
    hit = memo_skip(ctx, STAGE)
    assert hit is not None and hit[0] == "attempt_memo"
    verdict = evaluate_dispatch(ctx, STAGE, source="delivery_walk_to_master", layer="walk")
    assert verdict.refused and verdict.reason == "attempt_memo"


def test_progress_anywhere_in_the_run_clears_the_memo(tmp_path: Path) -> None:
    """The memo suppresses a re-offer at one state, never across real progress."""
    ctx = _ctx(tmp_path, "memo_progress")
    record_attempt(ctx, STAGE, outcome="failed")
    before = progress_token(ctx)
    assert memo_skip(ctx, STAGE) is not None
    mark_done_raw(ctx, "content_context")
    assert progress_token(ctx) != before
    assert memo_skip(ctx, STAGE) is None
    assert evaluate_dispatch(ctx, STAGE, source="walk", layer="walk").allowed


def test_changed_inputs_clear_the_memo(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "memo_inputs")
    record_attempt(ctx, STAGE, outcome="failed")
    assert memo_skip(ctx, STAGE) is not None
    manifest = ctx.final_path("segments", "manifest.json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_bytes(b'{"segments": []}')
    assert memo_skip(ctx, STAGE) is None


def test_memo_covers_stages_whose_inputs_are_still_unknown(tmp_path: Path) -> None:
    """40 of 72 stages have no known hard inputs; the memo still bounds their re-walk."""
    from interview_mux.dispatch_delta import input_digest, state_token

    ctx = _ctx(tmp_path, "memo_unknown_inputs")
    stage = "mastering_research_waves"
    assert input_digest(ctx, stage) is None
    record_attempt(ctx, stage, outcome="failed")
    assert memo_skip(ctx, stage) is not None
    # A heal that rewrites the stage's own artifact is a delta even with no contract.
    own = ctx.final_path("mastering", "research", "waves.json")
    own.parent.mkdir(parents=True, exist_ok=True)
    own.write_bytes(b'{"waves": [{"id": "w1"}]}')
    assert state_token(ctx, stage).startswith("own:")
    assert memo_skip(ctx, stage) is None


def test_memo_is_a_walk_layer_rule_only(tmp_path: Path) -> None:
    """An explicit re-dispatch (recovery, operator) is not a re-offer."""
    ctx = _ctx(tmp_path, "memo_layer")
    record_attempt(ctx, STAGE, outcome="failed")
    assert evaluate_dispatch(ctx, STAGE, source="walk", layer="walk").refused
    assert evaluate_dispatch(ctx, STAGE, source="operator", layer="dispatch").allowed


def test_operator_gates_are_never_refused_in_any_posture(tmp_path: Path) -> None:
    postures = (
        {"run_mode": "manual", "full_auto": False},
        {"run_mode": "partially-accelerated", "partial_auto": True, "full_auto": False},
        {"run_mode": "full-auto", "full_auto": True},
    )
    # ``missing_framing`` is a partial-auto pause gate id *and* a pipeline stage with
    # 22 dispatches in exec_11871. Its pause is enforced by the walk break, and the
    # stage itself stays governed by the door — so it is not in this exemption list.
    gate_ids = [
        g
        for g in (*PARTIAL_MUST_ACT_GATES, *PARTIAL_MAY_PAUSE_GATES)
        if g != "missing_framing"
    ]
    for idx, posture in enumerate(postures):
        ctx = _ctx(tmp_path, f"memo_gates_{idx}", **posture)
        for gate in gate_ids:
            # Blow every budget and memo for the gate id, then demand it still passes.
            for _ in range(9):
                append_ledger(ctx, {"kind": "stage", "identity": gate, "status": "started"})
            record_attempt(ctx, gate, outcome="refused")
            for layer in ("dispatch", "walk"):
                assert evaluate_dispatch(
                    ctx, gate, source="driver", layer=layer
                ).allowed, f"{posture['run_mode']} {gate} {layer}"


def test_door_binds_the_driver_postures_only(tmp_path: Path) -> None:
    assert door_applies(_ctx(tmp_path, "posture_full")) is True
    partial = _ctx(
        tmp_path,
        "posture_partial",
        run_mode="partially-accelerated",
        partial_auto=True,
        full_auto=False,
    )
    assert door_applies(partial) is True
    manual = _ctx(tmp_path, "posture_manual", run_mode="manual", full_auto=False)
    assert door_applies(manual) is False
    # …but the manual GUI process still walks under the door while the seed walk owns it.
    setattr(manual, "_homunculus_seed_walk", True)
    assert door_applies(manual) is True


def test_walk_advances_past_a_memoed_stage_with_a_defect(tmp_path: Path, monkeypatch) -> None:
    from interview_mux import pipeline
    from interview_mux.homunculus import agenda

    ctx = _ctx(tmp_path, "memo_walk")
    calls: list[str] = []
    monkeypatch.setattr(pipeline, "run_single_stage", lambda _c, sid: calls.append(sid))
    record_attempt(ctx, STAGE, outcome="failed", source="delivery_walk_to_master")

    agenda.walk_seed_agenda(ctx, [STAGE], reason="analysis_fill_delivery_prereqs")
    assert calls == []
    assert [d["stage"] for d in open_defects(ctx)] == [STAGE]

    # Real progress elsewhere re-opens it on the next re-entry.
    mark_done_raw(ctx, "content_context")
    agenda.walk_seed_agenda(ctx, [STAGE], reason="analysis_fill_delivery_prereqs")
    assert calls == [STAGE]


def test_walk_still_breaks_on_g0_before_the_door(tmp_path: Path, monkeypatch) -> None:
    """G0 stays operator-must-act: the gate break happens ahead of any refusal."""
    from interview_mux import pipeline
    from interview_mux.homunculus import agenda

    ctx = _ctx(tmp_path, "memo_g0")
    calls: list[str] = []
    monkeypatch.setattr(pipeline, "run_single_stage", lambda _c, sid: calls.append(sid))
    for _ in range(9):
        append_ledger(
            ctx, {"kind": "stage", "identity": "transcript_review", "status": "started"}
        )
    agenda.walk_seed_agenda(ctx, ["transcript_review", STAGE], reason="walk_seed_remainder")
    assert calls == []
    # The walk broke at the gate — it did not advance past it as a defect.
    assert [d["stage"] for d in open_defects(ctx)] == []
