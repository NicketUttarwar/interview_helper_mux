"""Postmortem hardening: VO loudness ownership, canned-bridge gate, anti-oscillation."""

from __future__ import annotations

import json
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
    monkeypatch.setattr(
        "interview_mux.vo_speech_qa.vo_passes_speech_qa",
        lambda *_a, **_k: True,
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
                    "text": "A complete thought about fundraising constraints.",
                    "topic": "fundraising constraints",
                    "type": "interviewee_answer",
                    "topic_tags": ["fundraising constraints"],
                    "flags": [],
                },
                {
                    "segment_id": "seg_b",
                    "start_ms": 120000,
                    "end_ms": 126000,
                    "speaker_id": "guest",
                    "speaker_role": "interviewee",
                    "text": "A later complete thought about the strategic sale.",
                    "topic": "the strategic sale",
                    "type": "interviewee_answer",
                    "topic_tags": ["the strategic sale"],
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


def test_canned_bridge_disabled_uses_grounded_contextual_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.seam_glue import mint_missing_transitions

    ctx = _reorder_ctx(tmp_path)
    patch_merged_config(
        monkeypatch,
        {"mastering": {"synthetic_framing": {"allow_canned_bridge_fallback": False}}},
    )
    doc = mint_missing_transitions(
        ctx, _MISSING_PAIR, transitions={"transitions": []}
    )
    text = doc["transitions"][0]["text"]
    assert "fundraising constraints" in text.casefold() or "strategic sale" in text.casefold()
    assert "what happened next" not in text.casefold()
    assert "what changed after that" not in text.casefold()
    assert doc["transitions"][0]["canned_bridge_fallback"] is False


def test_canned_bridge_enabled_still_replaces_unsafe_canned_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.seam_glue import mint_missing_transitions

    ctx = _reorder_ctx(tmp_path)
    patch_merged_config(
        monkeypatch,
        {"mastering": {"synthetic_framing": {"allow_canned_bridge_fallback": True}}},
    )
    doc = mint_missing_transitions(ctx, _MISSING_PAIR, transitions={"transitions": []})
    minted = list(doc["transitions"])
    assert len(minted) == 1
    text = minted[0]["text"]
    assert "fundraising constraints" in text.casefold() or "strategic sale" in text.casefold()
    assert minted[0]["canned_bridge_fallback"] is False
    assert minted[0]["spoken_copy_guard"]["action"] in {"allow", "fallback"}
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


def _synthetic_packet(ctx, *, ordered: list[str], required: list[dict]) -> dict:
    man = ctx.read_json("segments/manifest.json")
    by_id = {
        str(s["segment_id"]): s
        for s in (man.get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }
    return {
        "version": 1,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "selection_order_content_hash": ctx.read_json("master/selection.json")[
            "order_content_hash"
        ],
        "ordered_segment_ids": ordered,
        "selected_native_segments": [
            {
                "segment_id": sid,
                "start_ms": by_id.get(sid, {}).get("start_ms", 0),
                "end_ms": by_id.get(sid, {}).get("end_ms", 1000),
                "text": by_id.get(sid, {}).get("text", ""),
                "topic": by_id.get(sid, {}).get("topic", ""),
            }
            for sid in ordered
        ],
        "native_duration_ms": 11000,
        "policy": {"plan_after_native_selection": True},
        "required_reorder_seams": required,
    }


def test_normalize_keeps_reversed_llm_text_on_air_order_seam(tmp_path: Path) -> None:
    from interview_mux import synthetic_framing

    ctx = _reorder_ctx(tmp_path)
    packet = _synthetic_packet(
        ctx,
        ordered=["seg_a", "seg_b"],
        required=[{"after_segment_id": "seg_a", "before_segment_id": "seg_b"}],
    )
    llm_text = (
        "As we explore the evolution of cancer diagnostics, it's crucial to "
        "understand the limitations of traditional tissue biopsies."
    )
    plan = {
        "selection_order_content_hash": packet["selection_order_content_hash"],
        "lines": [
            {
                "line_id": "syn_reversed",
                "role": "bridge",
                "placement": "between_segments",
                "anchor_segment_id": "seg_a",
                "after_segment_id": "seg_b",
                "before_segment_id": "seg_a",
                "text": llm_text,
                "duration_ratio": 1.0,
                "comprehension_reason": "LLM bridge with swapped ids",
            }
        ],
    }
    out = synthetic_framing.normalize_synthetic_plan(ctx, plan, packet)
    lines = out["lines"]
    assert len(lines) == 1
    row = lines[0]
    assert row["after_segment_id"] == "seg_a"
    assert row["before_segment_id"] == "seg_b"
    assert "cancer diagnostics" in str(row["text"]).casefold()
    assert row.get("auto_minted_seam") is not True
    assert "what changed?" not in str(row["text"]).casefold()


def test_normalize_adopts_endpoint_messy_ids_onto_required_seam(tmp_path: Path) -> None:
    from interview_mux import synthetic_framing

    ctx = _reorder_ctx(tmp_path)
    packet = _synthetic_packet(
        ctx,
        ordered=["seg_a", "seg_b"],
        required=[{"after_segment_id": "seg_a", "before_segment_id": "seg_b"}],
    )
    llm_text = (
        "Liquid biopsy techniques change how clinicians sample tumor biology "
        "without invasive tissue collection."
    )
    plan = {
        "selection_order_content_hash": packet["selection_order_content_hash"],
        "lines": [
            {
                "line_id": "syn_follow",
                "role": "bridge",
                "placement": "between_segments",
                "anchor_segment_id": "seg_b",
                # Missing prior id — only following endpoint set.
                "after_segment_id": None,
                "before_segment_id": "seg_b",
                "text": llm_text,
                "duration_ratio": 1.0,
                "comprehension_reason": "bridge into next native",
            }
        ],
    }
    out = synthetic_framing.normalize_synthetic_plan(ctx, plan, packet)
    row = next(r for r in out["lines"] if r.get("line_id") == "syn_follow")
    assert row["after_segment_id"] == "seg_a"
    assert row["before_segment_id"] == "seg_b"
    assert "biopsy" in str(row["text"]).casefold()
    assert row.get("adopted_seam_repair") in {"endpoint", "anchor", "exact", "reversed"}


def test_normalize_drops_self_loop_and_validate_flags_bad_pairs(tmp_path: Path) -> None:
    from interview_mux import synthetic_framing

    ctx = _reorder_ctx(tmp_path)
    packet = _synthetic_packet(
        ctx,
        ordered=["seg_a", "seg_b"],
        required=[{"after_segment_id": "seg_a", "before_segment_id": "seg_b"}],
    )
    plan = {
        "selection_order_content_hash": packet["selection_order_content_hash"],
        "lines": [
            {
                "line_id": "syn_loop",
                "role": "bridge",
                "placement": "between_segments",
                "anchor_segment_id": "seg_a",
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_a",
                "text": "Turning to fundraising constraints, what changed?",
                "duration_ratio": 1.0,
                "comprehension_reason": "bad self loop",
            },
            {
                "line_id": "syn_ok",
                "role": "bridge",
                "placement": "between_segments",
                "anchor_segment_id": "seg_a",
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_b",
                "text": (
                    "Fundraising constraints reshape how teams prioritize the "
                    "strategic sale conversation."
                ),
                "duration_ratio": 1.0,
                "comprehension_reason": "valid seam",
            },
        ],
    }
    out = synthetic_framing.normalize_synthetic_plan(ctx, plan, packet)
    ids = {str(r.get("line_id")) for r in out["lines"]}
    assert "syn_loop" not in ids
    assert any(r.get("after_segment_id") == "seg_a" and r.get("before_segment_id") == "seg_b" for r in out["lines"])

    bad = {
        "selection_order_content_hash": packet["selection_order_content_hash"],
        "lines": [
            {
                "line_id": "syn_rev",
                "role": "bridge",
                "placement": "between_segments",
                "anchor_segment_id": "seg_a",
                "after_segment_id": "seg_b",
                "before_segment_id": "seg_a",
                "text": "A short bridge about the strategic sale path.",
                "duration_ratio": 1.0,
                "comprehension_reason": "reversed residual",
            }
        ],
    }
    errors = synthetic_framing.validate_synthetic_plan(ctx, bad, packet=packet)
    assert any("reversed air-order" in e or "self-loop" in e for e in errors)


def test_seam_glue_skips_self_loop_and_avoids_duplicate_stock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.seam_glue import mint_missing_transitions
    from interview_mux.spoken_copy_guard import artifact_spoken_copy_errors

    ctx = _reorder_ctx(tmp_path)
    patch_merged_config(
        monkeypatch,
        {"mastering": {"synthetic_framing": {"allow_canned_bridge_fallback": False}}},
    )
    planned_text = (
        "Fundraising constraints reshape how teams prioritize the strategic sale."
    )
    ctx.write_json(
        "understanding/synthetic_framing_plan.json",
        {
            "selection_order_content_hash": ctx.read_json("master/selection.json")[
                "order_content_hash"
            ],
            "strategy_summary": "test",
            "synthetic_input_share_estimate": 0.1,
            "lines": [
                {
                    "line_id": "syn_seam_seg_a_seg_b",
                    "role": "bridge",
                    "placement": "between_segments",
                    "after_segment_id": "seg_a",
                    "before_segment_id": "seg_b",
                    "anchor_segment_id": "seg_a",
                    "text": planned_text,
                    "duration_ratio": 1.0,
                    "target_duration_ms": 1200,
                    "native_respect_violation": False,
                    "comprehension_reason": "planned",
                }
            ],
        },
        skip_handoff=True,
    )
    doc = mint_missing_transitions(
        ctx,
        [
            {
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_b",
                "kind": "reorder",
                "source_gap_ms": 115000,
            },
            {
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_a",
                "kind": "reorder",
                "source_gap_ms": 1000,
            },
        ],
        transitions={"transitions": []},
    )
    pairs = {
        (str(t.get("after_segment_id")), str(t.get("before_segment_id")))
        for t in doc["transitions"]
    }
    assert ("seg_a", "seg_a") not in pairs
    assert ("seg_a", "seg_b") in pairs
    man = ctx.read_json("segments/manifest.json")
    by_id = {
        str(s["segment_id"]): s
        for s in (man.get("segments") or [])
        if isinstance(s, dict)
    }
    errs = artifact_spoken_copy_errors(
        gap_report=None,
        transitions=doc,
        segments_by_id=by_id,
        synthetic_framing=ctx.read_json("understanding/synthetic_framing_plan.json"),
    )
    assert not any("spoken_repeated_copy" in e for e in errs)
    assert not any("spoken_self_loop_seam" in e for e in errs)


def test_planned_transition_for_pair_rewrites_reversed_ids() -> None:
    from interview_mux.synthetic_framing import planned_transition_for_pair

    plan = {
        "lines": [
            {
                "line_id": "syn_rev",
                "placement": "between_segments",
                "after_segment_id": "seg_b",
                "before_segment_id": "seg_a",
                "text": "Bridge text.",
            }
        ]
    }
    row = planned_transition_for_pair(plan, "seg_a", "seg_b")
    assert row is not None
    assert row["after_segment_id"] == "seg_a"
    assert row["before_segment_id"] == "seg_b"
    assert row.get("adopted_seam_repair") == "reversed"


def test_assert_guarded_unions_seen_with_persisted_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux import spoken_copy_guard as scg

    ctx = _reorder_ctx(tmp_path)
    calls: list[dict] = []
    real_load = scg.load_persisted_spoken_texts

    def _tracking_load(*args, **kwargs):
        calls.append(dict(kwargs))
        return real_load(*args, **kwargs)

    monkeypatch.setattr(scg, "load_persisted_spoken_texts", _tracking_load)
    scg.assert_guarded_spoken_copy(
        "A grounded bridge about fundraising constraints and the strategic sale.",
        evidence={
            "before_topic": "fundraising constraints",
            "after_topic": "the strategic sale",
            "strict_grounding": True,
        },
        purpose="transition[seg_a->seg_b]",
        seen_texts=["unrelated prior line about weather patterns today"],
        ctx=ctx,
    )
    assert calls, "persisted corpus must be loaded even when seen_texts is provided"


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
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF" + (b"\0" * 128))
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
    monkeypatch.setattr(
        "interview_mux.air_order.assert_consumer", lambda ctx_, stage: None
    )

    from interview_mux.loud_fail import LoudStageFailure

    with pytest.raises(LoudStageFailure):
        junction_snip_qa.run_junction_snip_qa(ctx)
    report = ctx.read_json("master/junction_snip_qa.json")
    assert len(remasters) == 1, "identical repair signature must not remaster twice"
    assert int(report.get("remaster_rounds") or 0) == 1
    assert len(report.get("remediation_runs") or []) == 1
    budget = ctx.read_json("operator/junction_remaster_budget.json")
    assert budget.get("oscillation_halt") is True


def test_feel_and_commitment_remaster_honor_gen_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import junction_snip_qa
    from interview_mux.thrash_hardening import (
        JUNCTION_REMASTER_GEN_CAP,
        note_junction_remaster,
    )

    assert JUNCTION_REMASTER_GEN_CAP == 3
    ctx, _edl = _nudge_ctx(tmp_path)
    remasters: list[str] = []

    def _track_remaster(ctx_):
        remasters.append("mix")

    # Exhaust gen remaster budget before feel/commitment paths.
    for _ in range(JUNCTION_REMASTER_GEN_CAP):
        note_junction_remaster(ctx)

    monkeypatch.setattr(
        junction_snip_qa,
        "junction_snip_cfg",
        lambda cfg=None: {
            "mode": "advisory",
            "feel_audit_enabled": True,
            "apply_repairs": False,
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
        junction_snip_qa, "detect_junction_findings", lambda *a, **k: []
    )
    monkeypatch.setattr(
        junction_snip_qa, "remaster_mix_only", _track_remaster
    )
    monkeypatch.setattr(
        junction_snip_qa,
        "apply_feel_directives",
        lambda *a, **k: True,
    )
    # Force feel remaster past low_gain so GEN_CAP / hard_pin is exercised.
    monkeypatch.setattr(
        "interview_mux.timeline_reopen_meta_gate.decide_timeline_reopen",
        lambda *a, **k: {"allow": True, "reason": "unit_test"},
    )
    monkeypatch.setattr(
        junction_snip_qa,
        "run_junction_feel_audit",
        lambda ctx_, report, cfg=None: {
            "version": 1,
            "verdict": "revise",
            "llm_calls": 1,
            "directives": [{"action": "trim", "segment_id": "seg_a"}],
        },
    )
    monkeypatch.setattr(
        "interview_mux.failure_recovery.identify_all_failures",
        lambda ctx_, **kwargs: {"run_index": 1, "broken_pieces": []},
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
    monkeypatch.setattr(
        "interview_mux.air_order.assert_consumer", lambda ctx_, stage: None
    )
    # Force commitment remaster attempt (assembly older than EDL).
    asm = ctx.final_path("master", "assembly.wav")
    import os
    import time

    edl_path = ctx.final_path("master", "edl.json")
    older = time.time() - 60
    os.utime(asm, (older, older))
    os.utime(edl_path, None)

    junction_snip_qa.run_junction_snip_qa(ctx)
    report = ctx.read_json("master/junction_snip_qa.json")
    # Feel path must refuse past GEN_CAP; End-D commitment reseat still bypasses
    # budget/osc so assembly can match live EDL (exactly one remaster expected).
    assert report.get("feel_remaster_refused") is True
    assert remasters == ["mix"], "commitment remaster bypasses GEN_CAP (End-D)"
    meta = ctx.read_json("run_meta.json")
    # JSQ-B3: classified refuse — no needs_operator hang on budget exhaust.
    assert meta.get("needs_operator") is not True
    assert meta.get("junction_remaster_budget_exhausted") is True
    assert meta.get("junction_budget_exhaust_classified") is True


def test_third_gen_remaster_forbidden(tmp_path: Path) -> None:
    from interview_mux.thrash_hardening import (
        JUNCTION_REMASTER_GEN_CAP,
        junction_remaster_budget_ok,
        note_junction_remaster,
    )

    ctx = isolated_run_ctx(tmp_path, "exec_junc_cap3")
    (ctx.run_dir / "run_meta.json").write_text(
        json.dumps({"assembly_seating_generation": 1}), encoding="utf-8"
    )
    assert JUNCTION_REMASTER_GEN_CAP == 3
    for i in range(3):
        ok, used = junction_remaster_budget_ok(ctx)
        assert ok is True
        assert used == i
        note_junction_remaster(ctx)
    ok, used = junction_remaster_budget_ok(ctx)
    assert ok is False
    assert used == 3
