"""Comprehensive Land Honesty / hollow done / orphan promote coverage.

MUX_FORENSICS=0. Covers remaster unpaid land, remutate, stamp-alone,
shared-path, thin incompleteness matrix, G3 promote, advance/ESR/heal,
and positive control.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.artifact_repairs import repair_gap_report
from interview_mux.delivery_guardrails import (
    MUST_PRECEDE,
    promote_complete_orphan_stage_done,
    producer_ready,
    reconcile_delivery_batch,
    seed_stage_complete,
)
from interview_mux.delivery_invariants import (
    active_remutate_stages,
    live_producer_authority,
)
from interview_mux.done_authority import (
    GATE_MARKER_ONLY,
    LAYUP_AUTHORITY_STAGES,
    SHARED_PATH_PRODUCER_STAGES,
    land_honest,
    layup_authority_without_plan,
    may_clear_wait,
    may_skip_as_complete,
    shared_path_producer_mismatch,
    unpaid_land_blocks_promote,
    unpaid_land_reason,
)
from interview_mux.mix_junction_seat import (
    begin_remaster,
    clear_remaster,
    demote_hollow_mix_done,
    ensure_speech_first_remaster,
    mix_is_seed_complete,
    note_speech_first_mix,
    remaster_owner,
    speech_first_remaster_owed,
)
from interview_mux.nugget_layup import PLAN_REL
from interview_mux.pipeline import shared_analysis_chain_complete
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import stage_artifact_incompleteness
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER
from run_fixtures import isolated_run_ctx, mark_done_raw

_REPO = Path(__file__).resolve().parents[1]

_DISK_MAPPED_STAGES: list[str] = [
    sid
    for sid in list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    if sid in STAGE_ARTIFACT_DISK_PATHS and sid not in GATE_MARKER_ONLY
]

_JSON_SAMPLE_STAGES: list[str] = [
    sid
    for sid in _DISK_MAPPED_STAGES
    if str(STAGE_ARTIFACT_DISK_PATHS.get(sid) or "").endswith(".json")
][:6]

_MUST_PRECEDE_PRODUCERS: list[str] = sorted(
    {p for prods in MUST_PRECEDE.values() for p in prods}
)[:15]


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_land_honesty_comprehensive")


def _write_assembly(ctx: RunContext) -> Path:
    path = ctx.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)
    return path


def _write_raw_json(ctx: RunContext, rel: str, doc: dict) -> Path:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _mock_mix_seated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.air_order.mix_outputs_seated", lambda _c: True
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _sid: True,
    )


# ---------------------------------------------------------------------------
# 1. REMASTER unpaid_land_reason
# ---------------------------------------------------------------------------


def test_music_epoch_owner_blocks_mix_promote_despite_mtime_and_seated(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    assert ensure_speech_first_remaster(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"

    time.sleep(0.05)
    _write_assembly(ctx)
    _mock_mix_seated(monkeypatch)

    reason = unpaid_land_reason(ctx, "mix")
    assert reason is not None
    assert "remaster owed" in reason
    assert unpaid_land_blocks_promote(ctx, "mix") is True
    assert promote_complete_orphan_stage_done(ctx, ("mix",)) == []
    assert not ctx.is_done("mix")


def test_junction_owner_paid_for_junction_mix_still_unpaid(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S6(B): junction remaster owner is paid land for junction_snip_qa."""
    begin_remaster(ctx, owner="junction")
    _write_assembly(ctx)
    _mock_mix_seated(monkeypatch)
    for rel in ("master/junction_snip_qa.json", "master/seam_autopsy.json"):
        _write_raw_json(ctx, rel, {"version": 1, "generated_at": "t"})

    assert unpaid_land_reason(ctx, "mix") is not None
    assert unpaid_land_reason(ctx, "junction_snip_qa") is None
    assert promote_complete_orphan_stage_done(ctx, ("mix", "junction_snip_qa")) == []


def test_speech_first_remaster_owed_empty_owner_blocks_mix(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    _write_assembly(ctx)
    _mock_mix_seated(monkeypatch)

    assert remaster_owner(ctx) == ""
    assert speech_first_remaster_owed(ctx) is True
    assert unpaid_land_reason(ctx, "mix") is not None
    assert promote_complete_orphan_stage_done(ctx, ("mix",)) == []


def test_clear_remaster_clears_unpaid(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    begin_remaster(ctx, owner="junction")
    assert unpaid_land_reason(ctx, "mix") is not None
    clear_remaster(ctx)
    assert unpaid_land_reason(ctx, "mix") is None
    assert unpaid_land_reason(ctx, "junction_snip_qa") is None


def test_demote_hollow_mix_done_when_remaster_in_flight(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="junction")
    mark_done_raw(ctx, "mix")
    assert ctx.is_done("mix")
    _mock_mix_seated(monkeypatch)
    assert demote_hollow_mix_done(ctx) is True
    assert not ctx.is_done("mix")


def test_ensure_speech_first_remaster_demotes_marker(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    mark_done_raw(ctx, "mix")
    assert ctx.is_done("mix")
    assert ensure_speech_first_remaster(ctx) is True
    assert remaster_owner(ctx) == "music_epoch"
    assert not ctx.is_done("mix")


def test_mix_is_seed_complete_false_while_remaster_owed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="music_epoch")
    mark_done_raw(ctx, "mix")
    _write_assembly(ctx)
    _mock_mix_seated(monkeypatch)
    assert ctx.is_done("mix")
    assert mix_is_seed_complete(ctx) is False


def test_live_producer_authority_mix_false_while_remaster_owed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="junction")
    _write_assembly(ctx)
    _mock_mix_seated(monkeypatch)
    assert live_producer_authority(ctx, "mix") is False


# ---------------------------------------------------------------------------
# 2. REMUTATE
# ---------------------------------------------------------------------------


def test_active_remutate_blocks_mix_promote(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_raw_json(
        ctx,
        "mastering/edl_narrative_remutate.json",
        {
            "from_stage": "mix",
            "from_stages": ["mix", "junction_snip_qa"],
            "attempt": 1,
            "max_attempts": 3,
            "exhausted": False,
        },
    )
    _write_assembly(ctx)
    _mock_mix_seated(monkeypatch)

    assert "mix" in active_remutate_stages(ctx)
    assert unpaid_land_reason(ctx, "mix") is not None
    assert promote_complete_orphan_stage_done(ctx, ("mix",)) == []


# ---------------------------------------------------------------------------
# 3. STAMP-ALONE
# ---------------------------------------------------------------------------


def test_layup_authority_without_plan_unpaid_for_family(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [], "nugget_layup_authority": True},
    )
    assert not ctx.artifact_exists(PLAN_REL)
    assert layup_authority_without_plan(ctx) is True
    for sid in (
        "gap_framing_compose",
        "nugget_layup_compose",
        "optimal_questions",
    ):
        reason = unpaid_land_reason(ctx, sid)
        assert reason is not None
        assert "stamp-alone" in reason


def test_layup_plan_on_disk_clears_authority_without_plan(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [], "nugget_layup_authority": True},
    )
    _write_raw_json(ctx, PLAN_REL, {"version": 1, "slots": []})
    assert layup_authority_without_plan(ctx) is False
    assert unpaid_land_reason(ctx, "gap_framing_compose") is None
    assert unpaid_land_reason(ctx, "nugget_layup_compose") is None
    assert unpaid_land_reason(ctx, "optimal_questions") is None


def test_seed_missing_high_gap_clears_orphan_layup_authority(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    assert not ctx.artifact_exists(PLAN_REL)
    out: dict = {"nugget_layup_authority": True, "interviewer_lines": []}
    patched, applied = repair_gap_report(ctx, out)
    assert patched["nugget_layup_authority"] is False
    assert any(
        a.get("action") == "clear_orphan_nugget_layup_authority" for a in applied
    )


# ---------------------------------------------------------------------------
# 4. SHARED-PATH
# ---------------------------------------------------------------------------


def test_gap_report_sanitize_shared_path_mismatch(ctx: RunContext) -> None:
    _write_raw_json(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [],
            "_meta": {"producer_stage": "edl"},
        },
    )
    reason = unpaid_land_reason(ctx, "gap_report_sanitize")
    assert reason is not None
    assert "shared-path" in reason
    assert unpaid_land_blocks_promote(ctx, "gap_report_sanitize") is True


def test_gap_report_sanitize_framing_producer_is_paid(ctx: RunContext) -> None:
    """S1 co-producers (framing/layup) remain paid land for GRS promote."""
    _write_raw_json(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [],
            "_meta": {"producer_stage": "gap_framing_compose"},
        },
    )
    assert unpaid_land_reason(ctx, "gap_report_sanitize") is None
    assert unpaid_land_blocks_promote(ctx, "gap_report_sanitize") is False


def test_gap_report_sanitize_unsanitary_blocks_orphan_promote(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Paid producer is not enough — unsanitary gap still refuses orphan promote."""
    from interview_mux.stage_completion import stage_artifact_incompleteness

    _write_raw_json(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_dup",
                    "text": "hello there",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                    "gap_type": "missing_setup",
                },
                {
                    "line_id": "vo_dup2",
                    "text": "hello there",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                    "gap_type": "missing_setup",
                },
            ],
            "_meta": {"producer_stage": "gap_framing_compose"},
        },
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _s: True,
    )
    assert unpaid_land_reason(ctx, "gap_report_sanitize") is None
    inc = stage_artifact_incompleteness(ctx, "gap_report_sanitize")
    assert inc is not None
    assert "unsanitary" in inc or "sanitize" in inc
    assert promote_complete_orphan_stage_done(ctx, ("gap_report_sanitize",)) == []
    assert not ctx.is_done("gap_report_sanitize")


def test_air_contract_sanitize_shared_path_mismatch(ctx: RunContext) -> None:
    _write_raw_json(
        ctx,
        "mastering/mastering_plan.json",
        {
            "version": 1,
            "_meta": {"producer_stage": "air_script_compose"},
        },
    )
    reason = unpaid_land_reason(ctx, "air_contract_sanitize")
    assert reason is not None
    assert "shared-path" in reason
    assert unpaid_land_blocks_promote(ctx, "air_contract_sanitize") is True


def test_shared_path_matching_producer_stage_clears_unpaid(ctx: RunContext) -> None:
    _write_raw_json(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [],
            "_meta": {"producer_stage": "gap_report_sanitize"},
        },
    )
    assert unpaid_land_reason(ctx, "gap_report_sanitize") is None

    _write_raw_json(
        ctx,
        "mastering/mastering_plan.json",
        {
            "version": 1,
            "_meta": {"producer_stage": "air_contract_sanitize"},
        },
    )
    assert unpaid_land_reason(ctx, "air_contract_sanitize") is None


# ---------------------------------------------------------------------------
# 5. THIN INCOMPLETENESS FULL MATRIX
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sid", _DISK_MAPPED_STAGES)
def test_hollow_marker_not_seed_complete_or_ready(ctx: RunContext, sid: str) -> None:
    mark_done_raw(ctx, sid)
    assert seed_stage_complete(ctx, sid) is False
    assert land_honest(ctx, sid) is False
    assert producer_ready(ctx, sid) is False


@pytest.mark.parametrize("sid", _JSON_SAMPLE_STAGES)
def test_empty_json_primary_incompleteness(ctx: RunContext, sid: str) -> None:
    rel = STAGE_ARTIFACT_DISK_PATHS[sid]
    _write_raw_json(ctx, rel, {})
    mark_done_raw(ctx, sid)
    assert stage_artifact_incompleteness(ctx, sid) is not None
    assert seed_stage_complete(ctx, sid) is False


def test_zero_byte_primary_incompleteness(ctx: RunContext) -> None:
    sid = "transitions"
    rel = STAGE_ARTIFACT_DISK_PATHS[sid]
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    mark_done_raw(ctx, sid)
    assert stage_artifact_incompleteness(ctx, sid) is not None
    assert seed_stage_complete(ctx, sid) is False


# ---------------------------------------------------------------------------
# 6. PROMOTE / G3
# ---------------------------------------------------------------------------


def test_reconcile_delivery_batch_does_not_promote_mix_while_remaster_owed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="junction")
    _write_assembly(ctx)
    _mock_mix_seated(monkeypatch)
    assert not ctx.is_done("mix")
    reconcile_delivery_batch(ctx)
    assert not ctx.is_done("mix")
    assert unpaid_land_reason(ctx, "mix") is not None


def test_promote_honors_skip_set(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_remaster(ctx)
    _write_assembly(ctx)
    _mock_mix_seated(monkeypatch)
    promoted = promote_complete_orphan_stage_done(
        ctx, ("mix",), skip=frozenset({"mix"})
    )
    assert "mix" not in promoted
    assert not ctx.is_done("mix")


def test_source_lint_land_honesty_hooks() -> None:
    dg = (_REPO / "src" / "interview_mux" / "delivery_guardrails.py").read_text(
        encoding="utf-8"
    )
    da = (_REPO / "src" / "interview_mux" / "done_authority.py").read_text(
        encoding="utf-8"
    )
    assert "unpaid_land_blocks_promote" in dg
    assert "def unpaid_land_reason" in da
    assert "def may_skip_as_complete" in da
    # may_skip_as_complete must call land_honest (not bare is_done).
    skip_src = da.split("def may_skip_as_complete", 1)[1].split("\ndef ", 1)[0]
    assert "land_honest" in skip_src


# ---------------------------------------------------------------------------
# 7. ADVANCE / ESR / HEAL
# ---------------------------------------------------------------------------


def test_shared_analysis_chain_complete_false_on_hollow(ctx: RunContext) -> None:
    mark_done_raw(ctx, "episode_structure_compose")
    assert land_honest(ctx, "episode_structure_compose") is False
    assert shared_analysis_chain_complete(ctx) is False


def test_may_skip_and_may_clear_wait_false_on_hollow(ctx: RunContext) -> None:
    mark_done_raw(ctx, "episode_structure_compose")
    assert may_skip_as_complete(ctx, "episode_structure_compose") is False
    assert may_clear_wait(ctx, "episode_structure_compose") is False


@pytest.mark.parametrize("sid", _MUST_PRECEDE_PRODUCERS)
def test_producer_ready_false_on_hollow_must_precede(ctx: RunContext, sid: str) -> None:
    mark_done_raw(ctx, sid)
    if sid in GATE_MARKER_ONLY:
        return
    assert producer_ready(ctx, sid) is False


# ---------------------------------------------------------------------------
# 8. POSITIVE CONTROL
# ---------------------------------------------------------------------------


def test_positive_control_unpaid_clears_after_clear_remaster(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="junction")
    assert unpaid_land_reason(ctx, "mix") is not None
    clear_remaster(ctx)
    _write_assembly(ctx)
    _mock_mix_seated(monkeypatch)
    # Unpaid remaster obligation paid; promote may still fail incompleteness.
    assert unpaid_land_reason(ctx, "mix") is None


def test_heal_gap_compose_unmarks_hollow_stamp_alone(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """heal path must not leave hollow done when stamp-alone incompleteness open."""
    from interview_mux.stages.gaps import _heal_gap_framing_compose_if_complete

    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [], "nugget_layup_authority": True},
    )
    mark_done_raw(ctx, "gap_framing_compose")
    assert ctx.is_done("gap_framing_compose")
    with pytest.raises(Exception):
        _heal_gap_framing_compose_if_complete(ctx)
    # Hollow stamp must not remain seed-complete / land-honest.
    assert land_honest(ctx, "gap_framing_compose") is False
    assert seed_stage_complete(ctx, "gap_framing_compose") is False


def test_selection_order_sanitize_shared_path_mismatch(ctx: RunContext) -> None:
    _write_raw_json(
        ctx,
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001"],
            "_meta": {"producer_stage": "full_master_ranking"},
        },
    )
    reason = unpaid_land_reason(ctx, "selection_order_sanitize")
    assert reason is not None
    assert "shared-path" in reason
    assert unpaid_land_blocks_promote(ctx, "selection_order_sanitize") is True


def test_sound_design_plan_shared_path_mismatch(ctx: RunContext) -> None:
    _write_raw_json(
        ctx,
        "understanding/sound_design_plan.json",
        {
            "version": 1,
            "_meta": {"producer_stage": "sound_design_palettes"},
        },
    )
    reason = unpaid_land_reason(ctx, "sound_design_plan")
    assert reason is not None
    assert "shared-path" in reason


def test_exhausted_remutate_does_not_block_promote(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_raw_json(
        ctx,
        "mastering/edl_narrative_remutate.json",
        {
            "from_stage": "mix",
            "from_stages": ["mix"],
            "attempt": 9,
            "max_attempts": 3,
            "exhausted": True,
        },
    )
    clear_remaster(ctx)
    assert "mix" not in active_remutate_stages(ctx)
    # Remutate family unpaid should be clear (may still have other incompleteness).
    reason = unpaid_land_reason(ctx, "mix")
    assert reason is None or "remutate" not in reason


def test_census_doc_lists_land_honesty_apis() -> None:
    text = (_REPO / "src" / "interview_mux" / "done_authority.py").read_text(
        encoding="utf-8"
    )
    assert "unpaid_land_reason" in text
    assert "land_honest" in text


def test_i1_and_i10_cascade_modules_imported() -> None:
    """Smoke: cascade modules from Cluster A remain importable with Land Honesty."""
    import interview_mux.stages.gaps as gaps
    import interview_mux.mix_junction_seat as mjs
    import interview_mux.stage_completion as sc

    assert hasattr(gaps, "run_gap_framing_compose") or hasattr(
        gaps, "_heal_gap_framing_compose_if_complete"
    )
    assert hasattr(mjs, "music_epoch_pre_beds_seat")
    assert hasattr(sc, "_primary_artifact_thin_incompleteness")
    assert hasattr(sc, "stage_artifact_incompleteness")


# ---------------------------------------------------------------------------
# 9. REGRESSION GAPS — promote must honor unpaid; thin XC-HOLLOW; bare is_done
# ---------------------------------------------------------------------------

_SHARED_PATH_FIXTURES: list[tuple[str, str, str, dict]] = [
    (
        "gap_report_sanitize",
        "understanding/gap_report.json",
        "edl",
        {"interviewer_lines": []},
    ),
    (
        "air_contract_sanitize",
        "mastering/mastering_plan.json",
        "air_script_compose",
        {"version": 1},
    ),
    (
        "selection_order_sanitize",
        "master/selection.json",
        "full_master_ranking",
        {"ordered_segment_ids": ["seg_001"]},
    ),
    (
        "sound_design_plan",
        "understanding/sound_design_plan.json",
        "sound_design_palettes",
        {"version": 1},
    ),
]


def test_shared_path_and_layup_tables_match_expected() -> None:
    assert SHARED_PATH_PRODUCER_STAGES == frozenset(
        {
            "gap_report_sanitize",
            "air_contract_sanitize",
            "selection_order_sanitize",
            "sound_design_plan",
        }
    )
    assert LAYUP_AUTHORITY_STAGES == frozenset(
        {
            "gap_framing_compose",
            "nugget_layup_compose",
            "optimal_questions",
        }
    )


@pytest.mark.parametrize(
    "sid,rel,wrong_producer,base",
    _SHARED_PATH_FIXTURES,
    ids=[row[0] for row in _SHARED_PATH_FIXTURES],
)
def test_shared_path_mismatch_blocks_orphan_promote(
    ctx: RunContext,
    monkeypatch: pytest.MonkeyPatch,
    sid: str,
    rel: str,
    wrong_producer: str,
    base: dict,
) -> None:
    """Promote must refuse even when disk primary + outputs look present."""
    doc = dict(base)
    doc["_meta"] = {"producer_stage": wrong_producer}
    _write_raw_json(ctx, rel, doc)
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _s: True,
    )
    assert unpaid_land_blocks_promote(ctx, sid) is True
    assert promote_complete_orphan_stage_done(ctx, (sid,)) == []
    assert not ctx.is_done(sid)


@pytest.mark.parametrize(
    "sid,rel,wrong_producer,base",
    _SHARED_PATH_FIXTURES,
    ids=[row[0] for row in _SHARED_PATH_FIXTURES],
)
def test_shared_path_mismatch_surfaces_incompleteness(
    ctx: RunContext, sid: str, rel: str, wrong_producer: str, base: dict
) -> None:
    doc = dict(base)
    doc["_meta"] = {"producer_stage": wrong_producer}
    _write_raw_json(ctx, rel, doc)
    inc = stage_artifact_incompleteness(ctx, sid)
    assert inc is not None
    assert "shared-path" in inc
    assert land_honest(ctx, sid) is False


def test_shared_path_empty_producer_stage_is_unpaid(ctx: RunContext) -> None:
    """Empty/missing producer_stage on an existing shared primary is unpaid land."""
    _write_raw_json(
        ctx,
        "understanding/gap_report.json",
        {"interviewer_lines": [], "_meta": {"producer_stage": ""}},
    )
    reason = unpaid_land_reason(ctx, "gap_report_sanitize")
    assert reason is not None
    assert "shared-path" in reason
    assert "missing producer_stage" in reason
    assert unpaid_land_blocks_promote(ctx, "gap_report_sanitize") is True


def test_shared_path_missing_meta_producer_stage_is_unpaid(ctx: RunContext) -> None:
    """No _meta (or no producer_stage key) on existing primary → unpaid."""
    _write_raw_json(
        ctx,
        "understanding/gap_report.json",
        {"interviewer_lines": []},
    )
    mismatch = shared_path_producer_mismatch(ctx, "gap_report_sanitize")
    assert mismatch is not None
    assert "missing producer_stage" in mismatch
    assert unpaid_land_reason(ctx, "gap_report_sanitize") == mismatch


@pytest.mark.parametrize("sid", sorted(LAYUP_AUTHORITY_STAGES))
def test_stamp_alone_blocks_orphan_promote(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch, sid: str
) -> None:
    """Authority without plan must block promote — do not write PLAN_REL."""
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [], "nugget_layup_authority": True},
    )
    assert not ctx.artifact_exists(PLAN_REL)
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _s: True,
    )
    assert unpaid_land_blocks_promote(ctx, sid) is True
    assert promote_complete_orphan_stage_done(ctx, (sid,)) == []
    assert not ctx.is_done(sid)
    inc = stage_artifact_incompleteness(ctx, sid)
    assert inc is not None
    assert "stamp-alone" in inc


def test_layup_disabled_clears_stamp_alone_unpaid(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: False
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [], "nugget_layup_authority": True},
    )
    assert layup_authority_without_plan(ctx) is False
    for sid in LAYUP_AUTHORITY_STAGES:
        assert unpaid_land_reason(ctx, sid) is None


def test_active_remutate_unpaid_for_edl_blocks_promote(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_raw_json(
        ctx,
        "mastering/edl_narrative_remutate.json",
        {
            "from_stage": "edl",
            "from_stages": ["edl", "mix"],
            "attempt": 1,
            "max_attempts": 3,
            "exhausted": False,
        },
    )
    _write_raw_json(ctx, "master/edl.json", {"version": 1, "entries": []})
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, _s: True,
    )
    assert "edl" in active_remutate_stages(ctx)
    reason = unpaid_land_reason(ctx, "edl")
    assert reason is not None
    assert "remutate" in reason
    assert promote_complete_orphan_stage_done(ctx, ("edl",)) == []


def test_speech_first_owed_does_not_unpaid_junction_alone(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """speech_first_remaster_owed unpaid applies to mix only until owner stamps."""
    note_speech_first_mix(ctx)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete", lambda _c: True
    )
    assert remaster_owner(ctx) == ""
    assert speech_first_remaster_owed(ctx) is True
    assert unpaid_land_reason(ctx, "mix") is not None
    assert unpaid_land_reason(ctx, "junction_snip_qa") is None


def test_bare_is_done_with_remaster_is_not_land_honest(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    begin_remaster(ctx, owner="junction")
    mark_done_raw(ctx, "mix")
    _write_assembly(ctx)
    _mock_mix_seated(monkeypatch)
    assert ctx.is_done("mix") is True
    assert land_honest(ctx, "mix") is False
    assert may_clear_wait(ctx, "mix") is False
    assert may_skip_as_complete(ctx, "mix") is False


def test_xc_hollow_01_null_and_content_context_empty(ctx: RunContext) -> None:
    """XC-HOLLOW-01: null JSON + empty content_brief refuse seed-complete."""
    null_sid = "transitions"
    null_rel = STAGE_ARTIFACT_DISK_PATHS[null_sid]
    path = ctx.path(*null_rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("null", encoding="utf-8")
    mark_done_raw(ctx, null_sid)
    assert stage_artifact_incompleteness(ctx, null_sid) is not None
    assert seed_stage_complete(ctx, null_sid) is False

    cc = "content_context"
    cc_rel = STAGE_ARTIFACT_DISK_PATHS[cc]
    _write_raw_json(ctx, cc_rel, {})
    mark_done_raw(ctx, cc)
    assert stage_artifact_incompleteness(ctx, cc) is not None
    assert seed_stage_complete(ctx, cc) is False
    assert land_honest(ctx, cc) is False


def test_schema_thin_json_primary_incompleteness(ctx: RunContext) -> None:
    """Byte-thin JSON (<3) is schema-thin even before empty-object parse."""
    sid = "transitions"
    rel = STAGE_ARTIFACT_DISK_PATHS[sid]
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")  # 2 bytes
    mark_done_raw(ctx, sid)
    reason = stage_artifact_incompleteness(ctx, sid)
    assert reason is not None
    assert seed_stage_complete(ctx, sid) is False


def test_source_lint_advance_esr_heal_ban_bare_is_done() -> None:
    """Advance / ESR wait / skip paths must prefer Done Authority over bare is_done."""
    esr = (_REPO / "src" / "interview_mux" / "execution_status.py").read_text(
        encoding="utf-8"
    )
    pipe = (_REPO / "src" / "interview_mux" / "pipeline.py").read_text(encoding="utf-8")
    sc = (_REPO / "src" / "interview_mux" / "stage_completion.py").read_text(
        encoding="utf-8"
    )
    # ESR incomplete-after-conductor clear uses may_clear_wait.
    assert "may_clear_wait" in esr
    assert "only honest seed-complete clears wait" in esr or "Bare ``is_done``" in esr or (
        "never bare is_done" in esr
    )
    # Pipeline skip walk uses may_skip_as_complete (land_honest), not bare is_done.
    assert "may_skip_as_complete" in pipe
    assert "shared_analysis_chain_complete" in pipe
    # Heal incompleteness consults unpaid_land_reason before mark.
    assert "unpaid_land_reason" in sc
    assert "def heal_or_refuse_mark" in sc


@pytest.mark.parametrize("sid", sorted(SHARED_PATH_PRODUCER_STAGES))
def test_shared_path_table_wrong_producer_unpaid(ctx: RunContext, sid: str) -> None:
    rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)
    assert rel and str(rel).endswith(".json")
    _write_raw_json(
        ctx,
        str(rel),
        {"_meta": {"producer_stage": "__wrong_producer__"}, "version": 1},
    )
    mismatch = shared_path_producer_mismatch(ctx, sid)
    assert mismatch is not None
    assert "shared-path" in mismatch
    assert unpaid_land_reason(ctx, sid) == mismatch
    assert unpaid_land_blocks_promote(ctx, sid) is True
    mark_done_raw(ctx, sid)
    assert land_honest(ctx, sid) is False


@pytest.mark.parametrize("sid", sorted(SHARED_PATH_PRODUCER_STAGES))
def test_shared_path_matching_producer_clears_family(ctx: RunContext, sid: str) -> None:
    rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)
    assert rel
    _write_raw_json(
        ctx,
        str(rel),
        {"_meta": {"producer_stage": sid}, "version": 1},
    )
    assert shared_path_producer_mismatch(ctx, sid) is None
    reason = unpaid_land_reason(ctx, sid)
    assert reason is None or "shared-path" not in reason


@pytest.mark.parametrize("sid", sorted(LAYUP_AUTHORITY_STAGES))
def test_layup_authority_table_unpaid_without_plan(
    ctx: RunContext, sid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [], "nugget_layup_authority": True},
    )
    assert layup_authority_without_plan(ctx) is True
    reason = unpaid_land_reason(ctx, sid)
    assert reason is not None
    assert "stamp-alone" in reason
    assert unpaid_land_blocks_promote(ctx, sid) is True


def test_promote_source_wires_unpaid_land_gate() -> None:
    src = (
        _REPO / "src" / "interview_mux" / "delivery_guardrails.py"
    ).read_text(encoding="utf-8")
    assert "unpaid_land_blocks_promote" in src
    assert "Land Honesty" in src


def test_stage_completion_wires_unpaid_into_incompleteness() -> None:
    src = (
        _REPO / "src" / "interview_mux" / "stage_completion.py"
    ).read_text(encoding="utf-8")
    assert "unpaid_land_reason" in src
    assert "_primary_artifact_thin_incompleteness" in src