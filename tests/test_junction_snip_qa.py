"""Mastering Junction Snips — deterministic edge QA + O(1) feel audit."""

from __future__ import annotations

from interview_mux.junction_snip_qa import (
    _clip_end_text,
    apply_junction_repairs,
    detect_junction_findings,
    junction_snip_cfg,
    run_junction_snip_qa,
)
from interview_mux.order_hash import stamp_order_hash
from run_fixtures import isolated_run_ctx


def test_clip_end_text_tracks_remediated_edl_bound_not_static_segment_text():
    segment = {"text": "This static segment text ends if"}
    words = [
        {"text": "text", "start_ms": 800, "end_ms": 1000},
        {"text": "ends", "start_ms": 1000, "end_ms": 1200},
        {"text": "if", "start_ms": 1200, "end_ms": 1400},
        {"text": "we", "start_ms": 1400, "end_ms": 1600},
        {"text": "finish.", "start_ms": 1600, "end_ms": 1800},
    ]
    assert _clip_end_text(segment, words, 1400).endswith("if")
    assert _clip_end_text(segment, words, 1800).endswith("finish.")


def _seg(segment_id: str, *, start_ms: int, end_ms: int, text: str, speaker: str = "spk_0") -> dict:
    return {
        "segment_id": segment_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "speaker_id": speaker,
        "speaker_role": "interviewee",
        "type": "interviewee_answer",
        "text": text,
        "topic_tags": [],
        "flags": [],
    }


def _words_from_segments(segments: list[dict]) -> list[dict]:
    words: list[dict] = []
    for seg in segments:
        toks = str(seg["text"]).split()
        if not toks:
            continue
        span = max(1, int(seg["end_ms"]) - int(seg["start_ms"]))
        step = max(1, span // len(toks))
        t = int(seg["start_ms"])
        for tok in toks:
            words.append(
                {
                    "text": tok,
                    "start_ms": t,
                    "end_ms": t + step,
                    "speaker_id": seg.get("speaker_id"),
                }
            )
            t += step
    return words


def _base_ctx(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_junction_snip")
    segments = [
        _seg(
            "seg_002",
            start_ms=60000,
            end_ms=94140,
            text=(
                "And it was the point until then, whatever resources we had, we were putting "
                "in the company. So pretty much in India, we had very minimal resources or "
                "cash in the bank. To the extent at one point, the cash in our Bham account "
                "was higher than cash in our Mumbai account."
            ),
        ),
        _seg("seg_003", start_ms=94140, end_ms=94860, text="Okay."),
        _seg(
            "seg_004",
            start_ms=94860,
            end_ms=120000,
            text="Because everything was put back into the company I was very sure if",
        ),
        _seg(
            "seg_005",
            start_ms=120000,
            end_ms=135000,
            text="we could raise the round. That was the turning point for us.",
            speaker="spk_0",
        ),
    ]
    ctx.write_json("segments/manifest.json", {"segments": segments}, skip_handoff=True)
    ctx.write_json(
        "transcript/full.json",
        {"words": _words_from_segments(segments)},
        skip_handoff=True,
    )
    selection = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_002", "seg_003", "seg_004", "seg_005"],
            "chapters": [
                {"chapter_id": "ch1", "title": "Cash", "segment_ids": ["seg_002", "seg_003"]},
                {"chapter_id": "ch2", "title": "Raise", "segment_ids": ["seg_004", "seg_005"]},
            ],
        }
    )
    ctx.write_json("master/selection.json", selection, skip_handoff=True)
    # Continuum words after seg_004 incomplete end so on-a-roll / extend can fire
    return ctx, segments


def _edl_clips() -> list[dict]:
    return [
        {
            "type": "vo_pickup",
            "line_id": "vo_density_seg_003",
            "targets_segment_id": "seg_003",
            "placement": "before",
            "timeline_start_ms": 0,
            "duration_ms": 3000,
            "source_path": "vo_pickup/vo_density_seg_003.wav",
        },
        {
            "type": "speech",
            "segment_id": "seg_003",
            "source_start_ms": 94140,
            "source_end_ms": 94860,
            "timeline_start_ms": 3000,
            "duration_ms": 720,
        },
        {
            "type": "silence",
            "air_kind": "before_answer",
            "timeline_start_ms": 3720,
            "duration_ms": 1800,
        },
        {
            "type": "speech",
            "segment_id": "seg_002",
            "source_start_ms": 60000,
            "source_end_ms": 94140,
            "timeline_start_ms": 5520,
            "duration_ms": 34140,
        },
        {
            "type": "vo_pickup",
            "line_id": "vo_after_impact",
            "targets_segment_id": "seg_004",
            "placement": "before",
            "timeline_start_ms": 39660,
            "duration_ms": 2500,
            "source_path": "vo_pickup/vo_after.wav",
        },
        {
            "type": "speech",
            "segment_id": "seg_004",
            "source_start_ms": 94860,
            "source_end_ms": 120000,
            "timeline_start_ms": 42160,
            "duration_ms": 25140,
        },
        {
            "type": "speech",
            "segment_id": "seg_005",
            "source_start_ms": 120000,
            "source_end_ms": 135000,
            "timeline_start_ms": 67300,
            "duration_ms": 15000,
        },
        {
            "type": "silence",
            "air_kind": "chapter_hinge",
            "timeline_start_ms": 82300,
            "duration_ms": 5000,
        },
    ]


def test_detects_incomplete_vo_micro_impact_and_dead_air(tmp_path):
    ctx, _ = _base_ctx(tmp_path)
    # Impact beat: put seg_002 before VO in a cleaner stack for missing hold
    clips = [
        {
            "type": "speech",
            "segment_id": "seg_002",
            "source_start_ms": 60000,
            "source_end_ms": 94140,
            "timeline_start_ms": 0,
            "duration_ms": 34140,
        },
        {
            "type": "vo_pickup",
            "line_id": "vo_x",
            "targets_segment_id": "seg_003",
            "placement": "before",
            "timeline_start_ms": 34140,
            "duration_ms": 2000,
            "source_path": "vo_pickup/x.wav",
        },
        {
            "type": "speech",
            "segment_id": "seg_003",
            "source_start_ms": 94140,
            "source_end_ms": 94860,
            "timeline_start_ms": 36140,
            "duration_ms": 720,
        },
        {
            "type": "speech",
            "segment_id": "seg_004",
            "source_start_ms": 94860,
            "source_end_ms": 120000,
            "timeline_start_ms": 36860,
            "duration_ms": 25140,
        },
        {
            "type": "silence",
            "air_kind": "chapter_hinge",
            "timeline_start_ms": 62000,
            "duration_ms": 5000,
        },
    ]
    edl = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_002", "seg_003", "seg_004"],
            "clips": clips,
            "timeline_duration_ms": 67000,
        }
    )
    findings = detect_junction_findings(ctx, edl)
    kinds = {f["kind"] for f in findings}
    assert "incomplete_clause" in kinds or "on_a_roll" in kinds or "chapter_bleed_incomplete" in kinds
    assert "vo_micro" in kinds
    assert "missing_impact_hold" in kinds
    assert "dead_air_stack" in kinds


def test_apply_repairs_excludes_micro_and_inserts_hold(tmp_path):
    ctx, _ = _base_ctx(tmp_path)
    clips = [
        {
            "type": "speech",
            "segment_id": "seg_002",
            "source_start_ms": 60000,
            "source_end_ms": 94140,
            "timeline_start_ms": 0,
            "duration_ms": 34140,
        },
        {
            "type": "vo_pickup",
            "line_id": "vo_x",
            "targets_segment_id": "seg_003",
            "placement": "before",
            "timeline_start_ms": 34140,
            "duration_ms": 2000,
            "source_path": "vo_pickup/x.wav",
        },
        {
            "type": "speech",
            "segment_id": "seg_003",
            "source_start_ms": 94140,
            "source_end_ms": 94860,
            "timeline_start_ms": 36140,
            "duration_ms": 720,
        },
    ]
    edl = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_002", "seg_003"],
            "clips": clips,
            "timeline_duration_ms": 36860,
        }
    )
    ctx.write_json("master/edl.json", edl, skip_handoff=True)
    findings = detect_junction_findings(ctx, edl)
    conf = {**junction_snip_cfg(), "feel_audit_enabled": False, "apply_repairs": True}
    new_edl, applied, changed = apply_junction_repairs(ctx, edl, findings, cfg=conf)
    assert changed
    speech_ids = [
        c.get("segment_id") for c in new_edl["clips"] if c.get("type") == "speech"
    ]
    assert "seg_003" not in speech_ids
    holds = [
        c
        for c in new_edl["clips"]
        if c.get("type") == "silence" and c.get("air_kind") == "impact_hold"
    ]
    assert holds, "expected impact_hold after mic-drop"
    assert any(a.get("status") == "applied" for a in applied)


def test_music_hard_transition_finding(tmp_path):
    ctx, _ = _base_ctx(tmp_path)
    plan_path = ctx.path("understanding/sound_design_plan.json")
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    import json

    plan_path.write_text(
        json.dumps(
            {
                "flow_plans": {
                    "podcast": {
                        "cues": [
                            {
                                "asset_id": "theme_bed_1",
                                "placement": "under_segment",
                                "segment_id": "seg_002",
                                "role": "theme_bed",
                                "crossfade_ms": 20,
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    edl = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_002"],
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_002",
                    "source_start_ms": 60000,
                    "source_end_ms": 94140,
                    "timeline_start_ms": 0,
                    "duration_ms": 34140,
                }
            ],
            "timeline_duration_ms": 34140,
        }
    )
    findings = detect_junction_findings(ctx, edl)
    assert any(f.get("kind") == "music_hard_transition" for f in findings)


def test_stage_off_and_o1_llm_budget(tmp_path, monkeypatch):
    ctx, _ = _base_ctx(tmp_path)
    edl = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_002"],
            "clips": _edl_clips()[:1]
            + [
                {
                    "type": "speech",
                    "segment_id": "seg_002",
                    "source_start_ms": 60000,
                    "source_end_ms": 94140,
                    "timeline_start_ms": 0,
                    "duration_ms": 34140,
                }
            ],
            "timeline_duration_ms": 34140,
        }
    )
    # Fix clips to be valid
    edl["clips"] = [
        {
            "type": "speech",
            "segment_id": "seg_002",
            "source_start_ms": 60000,
            "source_end_ms": 94140,
            "timeline_start_ms": 0,
            "duration_ms": 34140,
        }
    ]
    ctx.write_json("master/edl.json", edl, skip_handoff=True)

    monkeypatch.setitem(
        __import__("interview_mux.config", fromlist=["merged_config"]).merged_config()
        .setdefault("mastering", {})
        .setdefault("junction_snip_qa", {}),
        "mode",
        "off",
    )
    # merged_config may be cached — patch junction_snip_cfg instead
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.junction_snip_cfg",
        lambda cfg=None: {
            "mode": "off",
            "feel_audit_enabled": False,
            "apply_repairs": False,
            "max_remaster_rounds": 2,
        },
    )
    run_junction_snip_qa(ctx)
    report = ctx.read_json("master/junction_snip_qa.json")
    assert report.get("skipped") is True
    assert report.get("llm_calls", 0) == 0

    # Advisory path with feel disabled — still O(1)
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.junction_snip_cfg",
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
        "interview_mux.junction_snip_qa.remaster_mix_only",
        lambda ctx: None,
    )
    run_junction_snip_qa(ctx)
    report = ctx.read_json("master/junction_snip_qa.json")
    assert int(report.get("llm_calls") or 0) <= 2


def test_multi_speaker_incomplete_detection(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_junction_multi")
    segments = [
        _seg("seg_a", start_ms=0, end_ms=5000, text="I think the real issue is if", speaker="spk_0"),
        _seg("seg_b", start_ms=5000, end_ms=12000, text="that we never shipped.", speaker="spk_1"),
    ]
    ctx.write_json("segments/manifest.json", {"segments": segments}, skip_handoff=True)
    ctx.write_json(
        "transcript/full.json",
        {"words": _words_from_segments(segments)},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        stamp_order_hash({"ordered_segment_ids": ["seg_a", "seg_b"], "chapters": []}),
        skip_handoff=True,
    )
    edl = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_a", "seg_b"],
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_a",
                    "source_start_ms": 0,
                    "source_end_ms": 5000,
                    "timeline_start_ms": 0,
                    "duration_ms": 5000,
                },
                {
                    "type": "speech",
                    "segment_id": "seg_b",
                    "source_start_ms": 5000,
                    "source_end_ms": 12000,
                    "timeline_start_ms": 5000,
                    "duration_ms": 7000,
                },
            ],
            "timeline_duration_ms": 12000,
        }
    )
    findings = detect_junction_findings(ctx, edl)
    assert any(
        f.get("segment_id") == "seg_a"
        and f.get("action") in {"extend_later", "cut_earlier", "merge_micro"}
        for f in findings
    )


def test_same_speaker_incomplete_prefers_merge_micro(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_junction_merge")
    segments = [
        _seg("seg_a", start_ms=0, end_ms=4000, text="I think the real issue is if", speaker="spk_0"),
        _seg("seg_b", start_ms=4200, end_ms=9000, text="we never shipped the release.", speaker="spk_0"),
    ]
    ctx.write_json("segments/manifest.json", {"segments": segments}, skip_handoff=True)
    # Transcript has no extend room after the incomplete cut — forces merge ladder.
    words = _words_from_segments([segments[0]])
    ctx.write_json("transcript/full.json", {"words": words}, skip_handoff=True)
    ctx.write_json(
        "master/selection.json",
        stamp_order_hash({"ordered_segment_ids": ["seg_a", "seg_b"], "chapters": []}),
        skip_handoff=True,
    )
    edl = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_a", "seg_b"],
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_a",
                    "source_start_ms": 0,
                    "source_end_ms": 4000,
                    "timeline_start_ms": 0,
                    "duration_ms": 4000,
                },
                {
                    "type": "speech",
                    "segment_id": "seg_b",
                    "source_start_ms": 4200,
                    "source_end_ms": 9000,
                    "timeline_start_ms": 4000,
                    "duration_ms": 4800,
                },
            ],
            "timeline_duration_ms": 8800,
        }
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa._find_last_complete_phrase_end",
        lambda *a, **k: None,
    )
    findings = detect_junction_findings(ctx, edl)
    merge = [f for f in findings if f.get("action") == "merge_micro"]
    assert merge, f"expected merge_micro, got {[f.get('action') for f in findings]}"
    new_edl, applied, changed = apply_junction_repairs(ctx, edl, merge)
    assert changed
    assert any(a.get("status") == "applied" for a in applied)
    speech_ids = [
        str(c.get("segment_id"))
        for c in (new_edl.get("clips") or [])
        if str(c.get("type") or "") == "speech"
    ]
    assert len(speech_ids) == 1


def test_exclude_reason_uses_finding_kind(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_junction_excl_reason")
    segments = [
        _seg("seg_ok", start_ms=0, end_ms=5000, text="We shipped the release."),
        _seg("seg_micro", start_ms=5000, end_ms=5200, text="Okay."),
    ]
    ctx.write_json("segments/manifest.json", {"segments": segments}, skip_handoff=True)
    ctx.write_json(
        "transcript/full.json",
        {"words": _words_from_segments(segments)},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        stamp_order_hash({"ordered_segment_ids": ["seg_ok", "seg_micro"], "chapters": []}),
        skip_handoff=True,
    )
    edl = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_ok", "seg_micro"],
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_ok",
                    "source_start_ms": 0,
                    "source_end_ms": 5000,
                    "timeline_start_ms": 0,
                    "duration_ms": 5000,
                },
                {
                    "type": "speech",
                    "segment_id": "seg_micro",
                    "source_start_ms": 5000,
                    "source_end_ms": 5200,
                    "timeline_start_ms": 5000,
                    "duration_ms": 200,
                },
            ],
            "timeline_duration_ms": 5200,
        }
    )
    findings = [
        {
            "kind": "vo_micro",
            "severity": "critical",
            "segment_id": "seg_micro",
            "action": "exclude_micro",
            "detail": {},
            "evidence": "test",
        }
    ]
    apply_junction_repairs(ctx, edl, findings)
    from interview_mux.nle_state import load_nle

    nle = load_nle(ctx)
    ov = (nle.get("segment_overrides") or {}).get("seg_micro") or {}
    assert ov.get("exclude_reason") == "junction_snip_qa:vo_micro"


def test_music_hard_transition_uses_effective_xf_after_placement(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_junction_music_xf")
    sdp_path = ctx.path("understanding", "sound_design_plan.json")
    sdp_path.parent.mkdir(parents=True, exist_ok=True)
    import json

    sdp_path.write_text(
        json.dumps(
            {
                "flow_plans": {
                    "podcast": {
                        "cues": [
                            {
                                "asset_id": "bed_a",
                                "placement": "under_segment",
                                "segment_id": "seg_1",
                                "role": "theme_bed",
                                "crossfade_ms": 0,
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    conf = {"music_soft_crossfade_ms": 180}
    from interview_mux.junction_snip_qa import _detect_music_transition_findings

    first = _detect_music_transition_findings(ctx, conf)
    assert any(f.get("kind") == "music_hard_transition" for f in first)

    def _patch(ctx2, asset_id, crossfade_ms):
        plan = json.loads(sdp_path.read_text(encoding="utf-8"))
        cue = plan["flow_plans"]["podcast"]["cues"][0]
        cue["crossfade_ms"] = max(int(cue.get("crossfade_ms") or 0), crossfade_ms)
        sdp_path.write_text(json.dumps(plan), encoding="utf-8")

    monkeypatch.setattr(
        "interview_mux.junction_snip_qa._patch_sdp_cue_crossfade",
        _patch,
    )
    from interview_mux.junction_snip_qa import _merge_placement_adjustments

    _merge_placement_adjustments(
        ctx,
        [
            {
                "asset_id": "bed_a",
                "action": "adjust_crossfade",
                "suggested_crossfade_ms": 180,
            }
        ],
    )
    second = _detect_music_transition_findings(ctx, conf)
    assert not any(f.get("kind") == "music_hard_transition" for f in second)
    plan = json.loads(sdp_path.read_text(encoding="utf-8"))
    cue = plan["flow_plans"]["podcast"]["cues"][0]
    assert int(cue.get("crossfade_ms") or 0) >= 180
    assert ctx.artifact_exists("sound_design/placement_adjustments.json")
