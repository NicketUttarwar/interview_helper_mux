"""vo_line_adjudicate S6/S7: honest stage_key + folded pre-synth stamps."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from interview_mux.stages import vo_line_adjudicate as vla_mod
from run_fixtures import isolated_run_ctx


def test_s6_rewrite_persists_as_adjudicate_not_synth_spoof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "vla_s6")
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "full_auto": True,
            "partial_auto": False,
            "voice_reference_approved_at": "2026-09-25T00:00:00Z",
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_rec_1",
                    "text": "Already settled spoken copy about the buyer reaction.",
                    "delivery": "record",
                    "targets_segment_id": "seg_001",
                }
            ]
        },
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.vo_path_ready",
        lambda *_a, **_k: (True, ""),
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.resolve_gap_vo_delivery",
        lambda *_a, **_k: "chatterbox",
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.voice_reference_approved",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_fill_was_skipped",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "interview_mux.automation_run.is_full_auto_run",
        lambda *_a, **_k: True,
    )

    seen: list[str] = []
    real_write = ctx.write_json

    def _capture_write(rel, data, **kwargs):
        if rel == "understanding/gap_report.json":
            seen.append(str(kwargs.get("stage_key") or ""))
        return real_write(rel, data, **kwargs)

    monkeypatch.setattr(ctx, "write_json", _capture_write)

    from interview_mux.gap_vo_gates import rewrite_full_auto_record_lines_to_synth

    ids = rewrite_full_auto_record_lines_to_synth(ctx, stage_key="vo_line_adjudicate")
    assert ids == ["vo_rec_1"]
    assert seen and all(s == "vo_line_adjudicate" for s in seen)
    assert "vo_synthesize" not in seen
    gap = ctx.read_json("understanding/gap_report.json")
    assert gap["interviewer_lines"][0]["delivery"] == "synthesize"


def test_s7_entry_calls_folded_stamp_suite_once() -> None:
    src = inspect.getsource(vla_mod.run_vo_line_adjudicate)
    assert "_pre_synth_gap_stamps" in src
    # Not the old double-call pattern.
    assert src.count("_prep_opening_orientation(ctx)") == 0
    assert src.count("_maybe_full_auto_record_to_synth(ctx)") == 0
    fold = inspect.getsource(vla_mod._pre_synth_gap_stamps)
    assert "_prep_opening_orientation" in fold
    assert "_maybe_full_auto_record_to_synth" in fold


def test_s6_helper_passes_adjudicate_stage_key() -> None:
    src = inspect.getsource(vla_mod._maybe_full_auto_record_to_synth)
    assert 'stage_key=STAGE_ID' in src or 'stage_key="vo_line_adjudicate"' in src


def test_homunculus_off_persists_skip_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """0.0.0 brain must stub adjudication so vo_synthesize is not blocked."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "vla_000")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.0.0", "full_auto": False},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime.has_homunculus_features",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(vla_mod, "_pre_synth_gap_stamps", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "interview_mux.stages.vo_line_adjudicate.heal_or_refuse_mark",
        lambda *_a, **_k: {"ok": True},
    )
    vla_mod.run_vo_line_adjudicate(ctx)
    assert ctx.artifact_exists("understanding/vo_line_adjudication.json")
    doc = ctx.read_json("understanding/vo_line_adjudication.json")
    assert str(doc.get("skip_reason") or "") == "homunculus_features_off"
