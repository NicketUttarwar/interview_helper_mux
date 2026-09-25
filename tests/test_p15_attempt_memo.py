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
    resume_after_intervene,
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


def test_product_fingerprint_mismatch_clears_attempt_memo(
    tmp_path: Path, monkeypatch
) -> None:
    """Cascade (MUX_FORENSICS=0): ownership/code patch must re-offer a refused fuse."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    ctx = _ctx(tmp_path, "memo_product_fp")
    record_attempt(ctx, "connector_fuse_pass", outcome="failed", source="analysis_fill_delivery_prereqs")
    assert memo_skip(ctx, "connector_fuse_pass") is not None

    monkeypatch.setattr(
        "interview_mux.dispatch_delta._live_product_stamps",
        lambda: ("patched_fp_deadbeef", "matrix_new_cafe"),
    )
    assert memo_skip(ctx, "connector_fuse_pass") is None
    assert evaluate_dispatch(
        ctx, "connector_fuse_pass", source="analysis_fill_delivery_prereqs", layer="walk"
    ).allowed


def test_legacy_memo_without_product_stamps_is_not_permanent(
    tmp_path: Path,
) -> None:
    """Pre-stamp refused rows (own:absent after AuthorityDenied) must retry after patch."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.dispatch_delta import MEMO_REL, progress_token, state_token
    from interview_mux.file_store import write_json as fs_write_json

    ctx = _ctx(tmp_path, "memo_legacy_stamps")
    # Simulate a pre-fix memo row that never stamped product/matrix.
    dest = Path(ctx.run_dir) / MEMO_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(
        dest,
        {
            "version": 1,
            "updated_at": "2026-09-18T19:35:05Z",
            "stages": {
                "connector_fuse_pass": {
                    "stage": "connector_fuse_pass",
                    "state_token": state_token(ctx, "connector_fuse_pass"),
                    "outcome": "refused",
                    "source": "analysis_fill_delivery_prereqs",
                    "progress_token": progress_token(ctx),
                    "attempts": 1,
                }
            },
        },
    )
    assert memo_skip(ctx, "connector_fuse_pass") is None
    assert evaluate_dispatch(
        ctx, "connector_fuse_pass", source="analysis_fill_delivery_prereqs", layer="walk"
    ).allowed

def test_forensics_restart_clears_failed_refused_memo(tmp_path: Path) -> None:
    """Cascade (MUX_FORENSICS=0): forensics sync must clear refused memo rows."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.dispatch_delta import clear_failed_refused_memo_rows, memo_skip
    from interview_mux.identical_failures import sync_identical_halts_with_product

    ctx = _ctx(tmp_path, "memo_forensics_clear")
    record_attempt(ctx, "mastering_shape_agenda", outcome="refused", source="walk")
    assert memo_skip(ctx, "mastering_shape_agenda") is not None
    assert clear_failed_refused_memo_rows(ctx) == 1
    assert memo_skip(ctx, "mastering_shape_agenda") is None

    record_attempt(ctx, "mastering_shape_agenda", outcome="failed", source="walk")
    result = sync_identical_halts_with_product(ctx, forensics=True)
    assert int(result.get("memo_cleared") or 0) >= 1
    assert memo_skip(ctx, "mastering_shape_agenda") is None


def test_memo_skip_yields_when_incompleteness_resumes_same_stage(
    tmp_path: Path, monkeypatch
) -> None:
    """Multi-shard producers must resume despite a refused memo (exec_13198 layup)."""
    stage = "nugget_layup_compose"
    ctx = _ctx(tmp_path, "memo_shard_resume")
    record_attempt(ctx, stage, outcome="refused", source="walk")
    assert memo_skip(ctx, stage) is not None

    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, st: (
            "layup_compose_shards_pending — resume nugget_layup_compose: (shard 1/2)"
            if st == stage
            else None
        ),
    )
    assert memo_skip(ctx, stage) is None
    assert evaluate_dispatch(ctx, stage, source="walk", layer="walk").allowed


def test_resume_after_intervene_clears_only_patched_stage_state(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "memo_intervene")
    record_attempt(ctx, "edl", outcome="failed", source="walk")
    record_attempt(ctx, "mix", outcome="refused", source="walk")
    ctx.write_json(
        "operator/sticky_heal.json",
        {
            "version": 1,
            "attempts": {
                "edl-key": {"pin": "edl", "halt": True},
                "mix-key": {"pin": "mix", "halt": True},
            },
            "active_halt": {"pin": "edl", "halt": True},
        },
        skip_handoff=True,
    )

    result = resume_after_intervene(ctx, stages=("edl",))

    assert result["memo_cleared"] == 1
    assert result["sticky_cleared"] == 1
    assert memo_skip(ctx, "edl") is None
    assert memo_skip(ctx, "mix") is not None
    sticky = ctx.read_json("operator/sticky_heal.json")
    assert sticky.get("active_halt") is None
    assert set(sticky["attempts"]) == {"mix-key"}


def test_resume_after_intervene_clears_selection_undo_and_refuse(
    tmp_path: Path,
) -> None:
    """CTA omit patches must unstick selection_commit_refused + authority_undo."""
    ctx = _ctx(tmp_path, "memo_selection_undo")
    ctx.write_json(
        "operator/selection_commit_refused.json",
        {
            "version": 1,
            "active": True,
            "stage": "nugget_layup_compose",
            "error": "authority_undo_thrash:master/selection.json: hash_oscillation:a↔b",
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "operator/authority_undo.json",
        {
            "version": 1,
            "artifacts": {
                "master/selection.json": {
                    "history": [
                        {"action": "media_ip_cta", "hash": "a"},
                        {"action": "nugget_layup_compose", "hash": "b"},
                    ],
                    "last": {"halt": True, "reason": "hash_oscillation:a↔b"},
                }
            },
            "active_halt": {"artifact": "master/selection.json", "pair": "a↔b"},
        },
        skip_handoff=True,
    )
    result = resume_after_intervene(ctx, stages=("nugget_layup_compose",))
    assert result.get("undo_cleared") == 1
    refused = ctx.read_json("operator/selection_commit_refused.json")
    assert refused.get("active") is False
    undo = ctx.read_json("operator/authority_undo.json")
    assert "master/selection.json" not in (undo.get("artifacts") or {})
    assert undo.get("active_halt") is None
