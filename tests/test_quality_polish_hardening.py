"""Postmortem hardening: VO loudness ownership, canned-bridge gate, anti-oscillation."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.order_hash import stamp_order_hash
from run_fixtures import isolated_run_ctx, patch_merged_config


# ── VO pickup loudness ownership ──────────────────────────────────────────────


def _pickup_ctx(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_vo_loudness")
    pickup = ctx.final_path("vo_pickup")
    pickup.mkdir(parents=True, exist_ok=True)
    (pickup / "line_001.wav").write_bytes(b"RIFF" + (b"\0" * 128))
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "line_001",
                    "delivery": "record",
                    "targets_segment_id": "seg_1",
                    "gap_type": "missing_framing",
                    "placement": "before",
                    "text": "Please clarify.",
                }
            ]
        },
        skip_handoff=True,
    )
    return ctx


def _captured_ffmpeg_filters(ctx, monkeypatch) -> list[str]:
    from interview_mux.stages.gaps import ingest_vo_pickup

    filters: list[str] = []

    def fake_run_command(cmd, **kwargs):
        if "-af" in cmd:
            filters.append(str(cmd[cmd.index("-af") + 1]))
        Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(cmd[-1]).write_bytes(b"RIFF" + (b"\0" * 128))
        return None

    monkeypatch.setattr(
        "interview_mux.operator_subprocess.run_command", fake_run_command
    )
    ingest_vo_pickup(ctx)
    return filters


def test_vo_ingest_skips_absolute_loudnorm_when_adjacent_match_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _pickup_ctx(tmp_path)
    patch_merged_config(
        monkeypatch,
        {
            "mix": {
                "normalize_vo_pickup": True,
                "vo_adjacent_level_match": {"enabled": True, "reference_window_ms": 4000},
            }
        },
    )
    filters = _captured_ffmpeg_filters(ctx, monkeypatch)
    assert filters, "expected a pickup conditioning pass"
    assert not any("loudnorm" in f for f in filters)
    assert any("aresample=48000" in f for f in filters)


def test_vo_ingest_applies_loudnorm_when_adjacent_match_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _pickup_ctx(tmp_path)
    patch_merged_config(
        monkeypatch,
        {
            "mix": {
                "normalize_vo_pickup": True,
                "vo_adjacent_level_match": {"enabled": False},
            }
        },
    )
    filters = _captured_ffmpeg_filters(ctx, monkeypatch)
    assert any("loudnorm=I=-18" in f for f in filters)


# ── Canned bridge fallback gate ───────────────────────────────────────────────


def _reorder_ctx(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_canned_bridge")
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_a",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "speaker_id": "guest",
                    "speaker_role": "interviewee",
                    "text": "A complete thought.",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "flags": [],
                },
                {
                    "segment_id": "seg_b",
                    "start_ms": 120000,
                    "end_ms": 126000,
                    "speaker_id": "guest",
                    "speaker_role": "interviewee",
                    "text": "A later complete thought.",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "flags": [],
                },
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        stamp_order_hash(
            {
                "version": 1,
                "ordered_segment_ids": ["seg_a", "seg_b"],
                "excluded_segment_ids": [],
                "chapters": [],
            }
        ),
        skip_handoff=True,
    )
    return ctx


_MISSING_PAIR = [
    {
        "after_segment_id": "seg_a",
        "before_segment_id": "seg_b",
        "kind": "reorder",
        "source_gap_ms": 115000,
    }
]


def test_canned_bridge_disabled_hard_stops_unplanned_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.loud_fail import LoudStageFailure
    from interview_mux.seam_glue import mint_missing_transitions

    ctx = _reorder_ctx(tmp_path)
    patch_merged_config(
        monkeypatch,
        {"mastering": {"synthetic_framing": {"allow_canned_bridge_fallback": False}}},
    )
    with pytest.raises(LoudStageFailure) as excinfo:
        mint_missing_transitions(ctx, _MISSING_PAIR, transitions={"transitions": []})
    assert "seg_a->seg_b" in str(excinfo.value)


def test_canned_bridge_enabled_mints_marked_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.seam_glue import CANNED_BRIDGE_TEXT, mint_missing_transitions

    ctx = _reorder_ctx(tmp_path)
    patch_merged_config(
        monkeypatch,
        {"mastering": {"synthetic_framing": {"allow_canned_bridge_fallback": True}}},
    )
    doc = mint_missing_transitions(ctx, _MISSING_PAIR, transitions={"transitions": []})
    minted = [t for t in doc["transitions"] if t.get("canned_bridge_fallback")]
    assert len(minted) == 1
    assert minted[0]["text"] == CANNED_BRIDGE_TEXT
    assert minted[0]["auto_minted"] is True


def test_validate_synthetic_plan_seam_coverage_follows_canned_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import synthetic_framing

    ctx = _reorder_ctx(tmp_path)
    ctx.write_json(
        synthetic_framing.CONTEXT_REL,
        {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00+00:00",
            "selection_order_content_hash": ctx.read_json("master/selection.json")[
                "order_content_hash"
            ],
            "ordered_segment_ids": ["seg_a", "seg_b"],
            "selected_native_segments": [],
            "native_duration_ms": 11000,
            "policy": {"plan_after_native_selection": True},
            "required_reorder_seams": [
                {"after_segment_id": "seg_a", "before_segment_id": "seg_b"}
            ],
        },
        skip_handoff=True,
    )
    plan = {
        "selection_order_content_hash": ctx.read_json("master/selection.json")[
            "order_content_hash"
        ],
        "lines": [],
    }

    monkeypatch.setattr(
        synthetic_framing,
        "synthetic_framing_cfg",
        lambda cfg=None: {
            "respect_native_speakers": True,
            "allow_canned_bridge_fallback": False,
            "duration_ratio_min": 0.4,
            "duration_ratio_max": 2.0,
        },
    )
    errors = synthetic_framing.validate_synthetic_plan(ctx, plan)
    assert any("required reorder seam missing planned line" in e for e in errors)

    monkeypatch.setattr(
        synthetic_framing,
        "synthetic_framing_cfg",
        lambda cfg=None: {
            "respect_native_speakers": True,
            "allow_canned_bridge_fallback": True,
            "duration_ratio_min": 0.4,
            "duration_ratio_max": 2.0,
        },
    )
    assert synthetic_framing.validate_synthetic_plan(ctx, plan) == []


# ── Anti-oscillation ──────────────────────────────────────────────────────────


def _nudge_ctx(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "exec_junction_hysteresis")
    segment = {
        "segment_id": "seg_a",
        "start_ms": 0,
        "end_ms": 5000,
        "speaker_id": "spk_0",
        "speaker_role": "interviewee",
        "type": "interviewee_answer",
        "text": "We shipped the release already.",
        "topic_tags": [],
        "flags": [],
    }
    words = []
    tokens = segment["text"].split()
    step = 5000 // len(tokens)
    for index, token in enumerate(tokens):
        words.append(
            {
                "text": token,
                "start_ms": index * step,
                "end_ms": (index + 1) * step,
                "speaker_id": "spk_0",
            }
        )
    ctx.write_json("segments/manifest.json", {"segments": [segment]}, skip_handoff=True)
    ctx.write_json("transcript/full.json", {"words": words}, skip_handoff=True)
    ctx.write_json(
        "master/selection.json",
        stamp_order_hash({"ordered_segment_ids": ["seg_a"], "chapters": []}),
        skip_handoff=True,
    )
    edl = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_a"],
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_a",
                    "source_start_ms": 0,
                    "source_end_ms": 4600,
                    "timeline_start_ms": 0,
                    "duration_ms": 4600,
                }
            ],
            "timeline_duration_ms": 4600,
        }
    )
    ctx.write_json("master/edl.json", edl, skip_handoff=True)
    return ctx, edl


def test_hysteresis_suppresses_repeat_nudge_on_settled_edge(tmp_path: Path) -> None:
    from interview_mux.junction_snip_qa import detect_junction_findings
    from interview_mux.nle_state import load_nle, save_nle

    ctx, edl = _nudge_ctx(tmp_path)
    first = [
        f
        for f in detect_junction_findings(ctx, edl)
        if f.get("action") == "nudge_source_bounds"
    ]
    assert first, "fixture must produce a word-boundary nudge"
    settled = first[0]
    edge = str(settled["detail"].get("edge") or "end")
    recommended = int(settled["detail"]["recommended_ms"])

    nle = load_nle(ctx)
    nle["junction_nudge_history"] = {
        f"seg_a:{edge}": {"applied_ms": recommended, "kind": settled.get("kind")}
    }
    save_nle(ctx, nle)
    assert not [
        f
        for f in detect_junction_findings(ctx, edl)
        if f.get("action") == "nudge_source_bounds"
        and str((f.get("detail") or {}).get("edge") or "end") == edge
    ]

    nle["junction_nudge_history"] = {
        f"seg_a:{edge}": {"applied_ms": recommended - 3000, "kind": settled.get("kind")}
    }
    save_nle(ctx, nle)
    assert [
        f
        for f in detect_junction_findings(ctx, edl)
        if f.get("action") == "nudge_source_bounds"
        and str((f.get("detail") or {}).get("edge") or "end") == edge
    ]


def test_feel_directives_do_not_renudge_settled_edges(tmp_path: Path) -> None:
    from interview_mux.junction_snip_qa import apply_feel_directives
    from interview_mux.nle_state import load_nle, save_nle

    ctx, _edl = _nudge_ctx(tmp_path)
    nle = load_nle(ctx)
    nle["junction_nudge_history"] = {"seg_a:end": {"applied_ms": 4000, "kind": "mid_word_end"}}
    save_nle(ctx, nle)
    audit = {
        "version": 1,
        "verdict": "revise",
        "directives": [
            {
                "action": "nudge_source_bounds",
                "severity": "warn",
                "segment_id": "seg_a",
                "detail": {"edge": "end", "recommended_ms": 4200},
                "evidence": "feel",
            }
        ],
    }
    assert apply_feel_directives(ctx, audit) is False


def test_oscillating_repair_signature_halts_remaster_thrash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import junction_snip_qa

    ctx, edl = _nudge_ctx(tmp_path)
    finding = {
        "kind": "mid_word_end",
        "severity": "critical",
        "segment_id": "seg_a",
        "clip_index": 0,
        "action": "nudge_source_bounds",
        "detail": {"edge": "end", "recommended_ms": 4400},
        "evidence": "test",
    }
    remasters: list[int] = []

    monkeypatch.setattr(
        junction_snip_qa,
        "junction_snip_cfg",
        lambda cfg=None: {
            "mode": "advisory",
            "feel_audit_enabled": False,
            "apply_repairs": True,
            "max_remaster_rounds": 2,
            "micro_nudge_ms": 2500,
            "phrase_extend_max_ms": 8000,
            "impact_hold_ms_min": 1200,
            "impact_hold_ms_max": 3500,
            "music_soft_crossfade_ms": 180,
            "dead_air_clamp_ms": 2500,
            "pace_multipliers": {"balanced": 1.0},
        },
    )
    monkeypatch.setattr(
        junction_snip_qa,
        "detect_junction_findings",
        lambda ctx_, edl_, cfg=None: [dict(finding)],
    )
    monkeypatch.setattr(
        junction_snip_qa,
        "apply_junction_repairs",
        lambda ctx_, edl_, findings_, cfg=None: (
            edl_,
            [{**finding, "status": "applied", "applied_ms": 4400, "edge": "end"}],
            True,
        ),
    )
    monkeypatch.setattr(
        junction_snip_qa, "remaster_mix_only", lambda ctx_: remasters.append(1)
    )
    monkeypatch.setattr(
        junction_snip_qa, "apply_feel_directives", lambda *a, **k: False
    )
    monkeypatch.setattr(
        junction_snip_qa,
        "run_junction_feel_audit",
        lambda ctx_, report, cfg=None: {
            "version": 1,
            "verdict": "pass",
            "llm_calls": 1,
            "directives": [],
        },
    )
    monkeypatch.setattr(
        "interview_mux.failure_recovery.identify_all_failures",
        lambda ctx_, **kwargs: {"run_index": kwargs.get("run_index", 1), "broken_pieces": []},
    )
    monkeypatch.setattr(
        "interview_mux.failure_recovery.plan_all_fixes", lambda ctx_, review: {}
    )
    monkeypatch.setattr(
        "interview_mux.seam_autopsy.build_autopsy",
        lambda ctx_, **kwargs: {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00+00:00",
            "phase": "post_junction",
            "seams": [],
            "blocking_reasons": [],
            "scores": {"finishability": 1.0},
            "commitment": {"status": "committed", "reasons": []},
        },
    )
    monkeypatch.setattr("interview_mux.seam_autopsy.write_autopsy", lambda ctx_, doc: None)
    monkeypatch.setattr(
        "interview_mux.seam_autopsy.enrich_ledger", lambda ctx_, doc: None
    )

    junction_snip_qa.run_junction_snip_qa(ctx)
    report = ctx.read_json("master/junction_snip_qa.json")
    assert len(remasters) == 1, "identical repair signature must not remaster twice"
    assert int(report.get("remaster_rounds") or 0) == 1
    assert len(report.get("remediation_runs") or []) == 1
