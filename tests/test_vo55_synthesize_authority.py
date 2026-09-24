"""Stage #55 VO synthesize authority root — bind-first / WAV-wins / flush / heal mark.

Covers exec_13177 footguns: pending WAV before promote, invalid_json_stdout accept,
policy omit still locked, process omit cleared, undeclared pickup flush, mark_done
without vo_fail_open_not_success chicken-egg.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.heal_success import may_mark_after_flush
from interview_mux.local_runtime import run_runtime_json
from interview_mux.run_context import RunContext
from interview_mux.vo_bind_authority import heal_seated_bind_mismatch
from interview_mux.vo_contract import (
    POLICY_OMIT_REASON_CODES,
    ensure_gap_line_on_air,
    omit_wins_skip_reason,
    policy_omit_skip_reason,
    repair_vo_contract_drift,
)
from interview_mux.write_staging import (
    enter_stage_staging,
    exit_stage_staging,
    flush_stage_writes,
    operator_visible_staging_path,
    staging_root,
)
from run_fixtures import (
    isolated_run_ctx,
    minimal_gap_line,
    minimal_gap_report,
    write_fixture_vo_wav,
)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "vo55_authority")


def test_seated_bind_synth_failed_not_in_policy_omit() -> None:
    assert "seated_bind_synth_failed" not in POLICY_OMIT_REASON_CODES
    row = {
        "skip_reason_code": "seated_bind_synth_failed",
        "skipped_optional": True,
        "air_script_omit": True,
    }
    assert policy_omit_skip_reason(row) is False
    assert omit_wins_skip_reason(row) is False
    cleared = ensure_gap_line_on_air(row, force_bind_synth_failed=True)
    assert not cleared.get("skipped_optional")
    assert not cleared.get("skip_reason_code")


def test_policy_cta_omit_stays_locked_even_with_wav(ctx: RunContext) -> None:
    wav = ctx.final_path("vo_pickup", "synthesized", "vo_layup_seg_cta.wav")
    write_fixture_vo_wav(wav)
    line = minimal_gap_line(
        line_id="vo_layup_seg_cta",
        text="Never reuse this CTA wording on air.",
        targets_segment_id="seg_cta",
        delivery="synthesize",
    )
    line["skipped_optional"] = True
    line["air_script_omit"] = True
    line["skip_reason_code"] = "never_touch_cta"
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(line),
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": [],
                    "omitted_line_ids": ["vo_layup_seg_cta"],
                    "orientation_id": None,
                }
            }
        },
        skip_handoff=True,
    )
    assert policy_omit_skip_reason(line) is True
    repair_vo_contract_drift(ctx)
    seats = (
        ctx.read_json("mastering/mastering_plan.json").get("air_script") or {}
    ).get("vo_seats") or {}
    assert "vo_layup_seg_cta" not in (seats.get("seated_line_ids") or [])
    assert "vo_layup_seg_cta" in (seats.get("omitted_line_ids") or [])
    gap = ctx.read_json("understanding/gap_report.json")
    row = gap["interviewer_lines"][0]
    assert row.get("skipped_optional")
    assert row.get("skip_reason_code") == "never_touch_cta"


def test_heal_accepts_pending_wav_before_promote(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pending stem under vo_synthesize counts — heal must not omit."""
    gap = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_layup_seg_003c",
            text="Pending take after chatterbox false JSON fail.",
            targets_segment_id="seg_003",
            delivery="synthesize",
        )
    )
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_003c"],
                    "omitted_line_ids": [],
                    "orientation_id": None,
                }
            }
        },
        skip_handoff=True,
    )
    enter_stage_staging("vo_synthesize")
    try:
        pending = (
            staging_root(ctx, "vo_synthesize")
            / "vo_pickup"
            / "synthesized"
            / "vo_layup_seg_003c.wav"
        )
        write_fixture_vo_wav(pending)
        monkeypatch.setattr(
            "interview_mux.stage_input_checks.compact_vo_coverage_stale_or_missing",
            lambda _ctx: ["vo_layup_seg_003c"],
        )

        def _boom(*_a, **_k):
            raise RuntimeError("false fail after pending wav write")

        monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _boom)

        heal = heal_seated_bind_mismatch(ctx, attempt_synth=True)
        assert "vo_layup_seg_003c" in heal["resynthesized"]
        assert heal["omitted"] == []
        committed = ctx.final_path(
            "vo_pickup", "synthesized", "vo_layup_seg_003c.wav"
        )
        assert committed.is_file(), "pending stem must promote before omit decision"
    finally:
        exit_stage_staging()


def test_run_runtime_json_accepts_usable_out_wav_on_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "line.wav"
    write_fixture_vo_wav(out)

    class _Proc:
        returncode = 0
        stdout = "pkg_resources is deprecated\n"
        stderr = ""

    monkeypatch.setattr(
        "interview_mux.local_runtime.run_runtime_script",
        lambda *_a, **_k: _Proc(),
    )
    result = run_runtime_json(
        "chatterbox",
        "tools/chatterbox_generate.py",
        {"out_wav": str(out), "text": "hello"},
        ctx=None,
        stage="vo_synthesize",
    )
    assert result.get("ok") is True
    assert result.get("out_wav") == str(out)
    assert result.get("accepted_despite")


def test_owner_flush_promotes_undeclared_vo_pickup_subpath(ctx: RunContext) -> None:
    """Even if StageInfo omitted a subpath, owner vo_pickup/** must flush."""
    assert operator_visible_staging_path(
        "vo_synthesize", "vo_pickup/matched/orphan.wav"
    )
    enter_stage_staging("vo_synthesize")
    try:
        pending = (
            staging_root(ctx, "vo_synthesize") / "vo_pickup" / "matched" / "orphan.wav"
        )
        write_fixture_vo_wav(pending)
        flushed = flush_stage_writes(ctx, "vo_synthesize")
        assert any(p.endswith("vo_pickup/matched/orphan.wav") for p in flushed)
        assert ctx.final_path("vo_pickup", "matched", "orphan.wav").is_file()
    finally:
        exit_stage_staging()


def test_may_mark_after_flush_complete_vo_no_fail_open_refuse(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First-time complete VO flush must not hit seed_stage_complete chicken-egg."""
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, _sid: None,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _ctx, _sid: True,
    )
    # Pretend seed_stage_complete still requires is_done (would chicken-egg).
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, _sid: False,
    )
    ok, reason = may_mark_after_flush(
        ctx, "vo_synthesize", resilience_action="continue", acceptance_ok=True
    )
    assert ok is True
    assert reason == "ok"
    assert "vo_fail_open_not_success" not in reason


def test_may_mark_after_flush_still_refuses_incompleteness(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, _sid: "g1_open: missing wav",
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _ctx, _sid: True,
    )
    ok, reason = may_mark_after_flush(
        ctx, "vo_synthesize", resilience_action="continue", acceptance_ok=True
    )
    assert ok is False
    assert reason == "flush_refuse:incompleteness"
