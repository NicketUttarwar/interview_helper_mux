"""MUST_PRECEDE / edl_ready ordering contract (exec_13165 WS2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import (
    EDL_CONSUMERS,
    MUST_PRECEDE,
    edl_ready,
    filter_delivery_candidates,
    producer_ready,
    seed_stage_complete,
)
from interview_mux.delivery_invariants import seed_order_consumer_for
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "must_precede")


@pytest.mark.parametrize("consumer", sorted(EDL_CONSUMERS))
def test_edl_consumers_deferred_without_seed_complete_edl(
    ctx, monkeypatch: pytest.MonkeyPatch, consumer: str
) -> None:
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid not in {"edl", "edl_narrative_audit"},
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _c: (True, "ok"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.ship_path_ready",
        lambda _c: (False, "no_master"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _c: True,
    )
    filtered = filter_delivery_candidates(ctx, [consumer, "edl"])
    assert consumer not in filtered
    assert filtered
    assert filtered[0] in {"edl", "edl_narrative_audit"}


def test_hollow_edl_json_does_not_unlock_delight(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_13165: artifact_exists edl.json must not unlock consumers."""
    master = ctx.path("master")
    master.mkdir(parents=True, exist_ok=True)
    (master / "edl.json").write_text('{"clips":[]}', encoding="utf-8")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.ship_path_ready",
        lambda _c: (False, "no_master"),
    )
    assert not edl_ready(ctx)
    filtered = filter_delivery_candidates(
        ctx, ["assembly_preview", "listen_delight_audit"]
    )
    assert "assembly_preview" not in filtered
    assert "listen_delight_audit" not in filtered


def test_sdp_restamp_resumes_music_not_mix(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid == "sound_design_plan",
    )
    pin = seed_order_consumer_for(ctx, "sound_design_plan", message="complete sound_design_plan before running mix")
    assert pin in {"music_palette_compose", "sfx_prompt_craft", "mmaudio_sfx"}
    assert pin != "mix"


def test_must_precede_table_covers_edl_spine() -> None:
    assert "edl" in MUST_PRECEDE["assembly_preview"]
    assert "edl" in MUST_PRECEDE["listen_delight_audit"]
    assert "vo_synthesize" in MUST_PRECEDE["edl"]
    assert producer_ready is seed_stage_complete or callable(producer_ready)
    # Always-HAU: beds are not producers of mix (exec_13170 follow-through).
    assert MUST_PRECEDE["mix"] == ("edl",)
    assert "mmaudio_sfx" not in MUST_PRECEDE["mix"]
    assert "music_palette_compose" not in MUST_PRECEDE["mix"]


# --- Expanded WS2 (non-EDL attached-plan collision set) ---


@pytest.mark.parametrize(
    "consumer,producer",
    [
        ("air_script_compose", "selection_order_sanitize"),
        ("gap_report_sanitize", "nugget_layup_compose"),
        ("air_contract_sanitize", "air_script_seams"),
        ("sound_design_vo_finalize", "vo_synthesize"),
        ("vo_synthesize", "vo_line_adjudicate"),
        ("edl_narrative_audit", "sound_design_vo_finalize"),
    ],
)
def test_must_precede_sanitize_vo_spine_defers_consumer(
    ctx, monkeypatch: pytest.MonkeyPatch, consumer: str, producer: str
) -> None:
    """Expanded WS2 O21/O22: sanitize + VO spine MUST_PRECEDE (not EDL_CONSUMERS)."""
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid != producer,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _c: (False, "phase_a_unsealed"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.ship_path_ready",
        lambda _c: (False, "no_master"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _c: False,
    )
    filtered = filter_delivery_candidates(ctx, [consumer, producer])
    assert consumer not in filtered
    assert producer in filtered or filtered == [producer] or (
        filtered and filtered[0] == producer
    )


def test_delivery_stable_requires_adjudicate_seed_complete(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O3: is_done alone must not clear vo_adjudicate_incomplete."""
    from interview_mux.delivery_guardrails import delivery_stable_for_music

    done = {"nugget_layup_compose"}
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid in done,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: [],
    )
    # Marker present but not seed-complete.
    marker = ctx.final_path(".stage_done", "vo_line_adjudicate")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    ok, reason = delivery_stable_for_music(ctx)
    assert not ok
    assert reason == "vo_adjudicate_incomplete"


def test_g1_green_does_not_seed_complete_adjudicate_for_music(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O8: seal_adjudicate anti-purge ≠ adjudicate seed_complete for music."""
    from interview_mux.delivery_guardrails import (
        delivery_stable_for_music,
        seal_adjudicate_stale_when_g1_green,
    )

    und = ctx.path("understanding")
    und.mkdir(parents=True, exist_ok=True)
    (und / "vo_line_adjudication.json").write_text(
        '{"version":1,"lines":[],"_meta":{"stale":true,'
        '"stale_reason":"invalidated_by:nugget_layup_compose"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: [],
    )
    assert seal_adjudicate_stale_when_g1_green(ctx) is True
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid == "nugget_layup_compose",
    )
    ok, reason = delivery_stable_for_music(ctx)
    assert not ok
    assert reason == "vo_adjudicate_incomplete"


def test_path_to_master_pins_phase_a_not_music(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O7: incomplete Phase A producer beats music ladder on seal-only skew."""
    from interview_mux.thrash_hardening import path_to_master_pin

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _c: (False, "phase_a_unsealed"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid not in {"vo_line_adjudicate", "edl", "listen_delight_audit"},
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _c: False,
    )
    pin = path_to_master_pin(ctx)
    assert pin not in {
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "mix",
    }
    assert pin in {
        "vo_line_adjudicate",
        "vo_synthesize",
        "edl",
        "edl_narrative_audit",
        "listen_delight_audit",
        "assembly_preview",
        "nugget_layup_compose",
        "sound_design_plan",
        "sound_design_vo_finalize",
    }


def test_earliest_incomplete_does_not_skip_vo_for_edl(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O10: assembly WAV present must not skip incomplete vo_synthesize for edl."""
    from interview_mux.llm_flow_hardening import _earliest_incomplete_seed_stage

    master = ctx.path("master")
    master.mkdir(parents=True, exist_ok=True)
    (master / "assembly.wav").write_bytes(b"RIFF")
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.ANALYSIS_ORDER",
        (),
    )
    # Patch is_done / incompleteness via seed path: mark everything before VO done.
    from interview_mux.v2.config import DELIVERY_ORDER

    before_vo = []
    for sid in DELIVERY_ORDER:
        if sid == "vo_synthesize":
            break
        before_vo.append(sid)
        marker = ctx.final_path(".stage_done", sid)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid in before_vo,
    )
    monkeypatch.setattr(
        "interview_mux.gates.check_g1_vo",
        lambda _c: ["vo_line_x"],
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _c, sid: (
            "transition pairs missing: a→b" if sid == "vo_synthesize" else None
        ),
    )
    earliest = _earliest_incomplete_seed_stage(ctx, "edl")
    assert earliest == "vo_synthesize"


def test_music_epoch_does_not_raw_reseat_incomplete(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O12: stamp+SDP trusts epoch but must not raw-touch hollow music markers."""
    from interview_mux.delivery_guardrails import MUSIC_BEFORE_MIX, music_epoch_complete

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.read_delivery_epoch",
        lambda _c: {"music_complete_at": "2026-01-01T00:00:00Z"},
    )
    monkeypatch.setattr(
        "interview_mux.sdp_cross_validate.missing_sdp_asset_wavs",
        lambda _c: [],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: False,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _c, sid: False,
    )
    assert music_epoch_complete(ctx) is True
    for sid in MUSIC_BEFORE_MIX:
        assert not ctx.is_done(sid)


def test_vo_finalize_stage_input_requires_synthesize(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O21: sound_design_vo_finalize input check gates on vo_synthesize."""
    from interview_mux.stage_input_checks import collect_stage_input_issues

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: False,
    )
    issues = collect_stage_input_issues(ctx, "sound_design_vo_finalize")
    assert any("vo_synthesize" in i.message for i in issues)


def test_from_stage_reinjects_incomplete_must_precede(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O19: consumer with incomplete MUST_PRECEDE producer yields that hole."""
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid not in {"vo_synthesize", "edl", "edl_narrative_audit"},
    )
    monkeypatch.setattr(
        "interview_mux.delivery_invariants.committed_master_wav",
        lambda _c: False,
    )
    from interview_mux.delivery_guardrails import earliest_incomplete_must_precede

    hole = earliest_incomplete_must_precede(ctx, "edl")
    assert hole in {"vo_synthesize", "edl_narrative_audit", "sound_design_vo_finalize"}


def test_sticky_seed_mark_refuses_hollow(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O18: sticky mark only when heal/seed-complete succeeds."""
    from interview_mux.seed_policy import ensure_sticky_seed_mark

    monkeypatch.setattr(
        "interview_mux.seed_policy.seed_stage_satisfied_by_policy",
        lambda _c, sid: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: False,
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.heal_or_refuse_mark",
        lambda _c, sid, force=False: {"refused": True, "reason": "incomplete"},
    )
    assert ensure_sticky_seed_mark(ctx, "vo_line_adjudicate") is False


def test_premature_cap_applies_regardless_of_automation_flag() -> None:
    """O15: premature_cap applies to automation and GUI via shared helper."""
    import inspect

    from interview_mux.web import runner as runner_mod

    src = inspect.getsource(runner_mod.JobRunner)
    assert "apply_premature_cap_for_execute" in src
    assert "Expanded WS2 O15" in src
    # Must not be gated solely inside `if not automation_driver_run` block.
    assert "premature_cap applies to automation and GUI" in src


# --- DP-LAYUP-ADJ A: order leapfrog seal ---


def test_vo_synth_defers_to_incomplete_layup(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synth candidate with incomplete layup → filtered to layup (not synth)."""
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid not in {
            "nugget_layup_compose",
            "transitions",
            "sound_design_plan",
            "vo_line_adjudicate",
            "vo_synthesize",
        },
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _c: (False, "layup_incomplete"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.ship_path_ready",
        lambda _c: (False, "no_master"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _c: False,
    )
    filtered = filter_delivery_candidates(
        ctx, ["vo_synthesize", "nugget_layup_compose"]
    )
    assert "vo_synthesize" not in filtered
    assert filtered and filtered[0] == "nugget_layup_compose"


def test_vo_synth_defers_to_incomplete_adjudicate(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Layup+transitions+SDP complete, adjudicate open → synth deferred to adjudicate."""
    done = {
        "nugget_layup_compose",
        "transitions",
        "sound_design_plan",
        "air_contract_sanitize",
    }
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid in done,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_stable_for_music",
        lambda _c: (False, "vo_adjudicate_incomplete"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.phase_a_sealed",
        lambda _c: False,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.ship_path_ready",
        lambda _c: (False, "no_master"),
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_epoch_complete",
        lambda _c: False,
    )
    # transitions.json present so G8 does not reclaim to transitions.
    master = ctx.path("master")
    master.mkdir(parents=True, exist_ok=True)
    (master / "transitions.json").write_text("{}", encoding="utf-8")
    filtered = filter_delivery_candidates(
        ctx, ["vo_synthesize", "vo_line_adjudicate"]
    )
    assert "vo_synthesize" not in filtered
    assert "vo_line_adjudicate" in filtered


def test_clamp_resume_synth_to_layup_when_incomplete(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import clamp_resume_through_order
    from interview_mux.thrash_hardening import heal_navigate, resume_producer

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid != "nugget_layup_compose",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: False,
    )
    assert clamp_resume_through_order(ctx, "vo_synthesize") == "nugget_layup_compose"
    assert resume_producer(ctx, "vo_synthesize") == "nugget_layup_compose"
    nav = heal_navigate(
        ctx,
        error="seed_order_prereq: complete vo_synthesize before mix",
        stage="vo_synthesize",
        intent="seed_order_prereq",
    )
    assert nav["from_stage"] == "nugget_layup_compose"


def test_clamp_resume_transitions_stale_from_layup(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G8 stale-from-layup → clamp synth pin to transitions (not leapfrog)."""
    from interview_mux.delivery_guardrails import clamp_resume_through_order

    done = {
        "nugget_layup_compose",
        "sound_design_plan",
        "vo_line_adjudicate",
        "air_contract_sanitize",
    }
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _c, sid: sid in done or sid == "transitions",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_open",
        lambda _c: False,
    )
    master = ctx.path("master")
    master.mkdir(parents=True, exist_ok=True)
    (master / "transitions.json").write_text(
        '{"_meta":{"stale_reason":"invalidated_by:nugget_layup_compose"}}',
        encoding="utf-8",
    )
    assert clamp_resume_through_order(ctx, "vo_synthesize") == "transitions"
