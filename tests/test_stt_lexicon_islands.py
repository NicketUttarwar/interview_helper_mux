"""STT lexicon-island scanner, soft priors, and selection guards."""

from __future__ import annotations

from run_fixtures import isolated_run_ctx

from interview_mux.stt_lexicon_islands import (
    BOOSTS_PATH,
    ISLANDS_PATH,
    build_stt_trust_priors,
    enforce_stt_island_selection_guards,
    scan_stt_lexicon_groups,
    soft_protect_segment_ids,
)


def _seg(sid: str, *, start_ms: int, end_ms: int, text: str = "", **extra) -> dict:
    row = {
        "segment_id": sid,
        "type": "interviewee_answer",
        "speaker_id": "spk_00",
        "speaker_role": "interviewee",
        "start_ms": start_ms,
        "end_ms": end_ms,
        "topic_tags": [],
        "text": text,
    }
    row.update(extra)
    return row


def _words_padded_island(*, island_text: str = "myocardial", island_conf: float = 0.35) -> list[dict]:
    """High-conf pads around a low-conf island (same speaker)."""
    seq = [
        ("The", 0.95),
        ("patient", 0.94),
        ("received", 0.93),
        (island_text, island_conf),
        ("therapy", 0.94),
        ("yesterday", 0.95),
        ("morning", 0.96),
    ]
    words = []
    t = 0
    for text, conf in seq:
        words.append(
            {
                "text": text,
                "start_ms": t,
                "end_ms": t + 400,
                "speaker_id": "spk_00",
                "confidence": conf,
            }
        )
        t += 400
    return words


def test_scan_padded_lexicon_candidate_and_nonfit(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_stt_island")
    ctx.write_json("transcript/full.json", {"words": _words_padded_island()})
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                _seg(
                    "seg_042",
                    start_ms=0,
                    end_ms=2800,
                    text="The patient received myocardial therapy yesterday morning",
                )
            ]
        },
    )
    doc = scan_stt_lexicon_groups(ctx)
    assert doc["mode"] == "evaluate_all_groups_soft_boost_only"
    assert ctx.artifact_exists(ISLANDS_PATH)
    fits = [g for g in doc["groups"] if g.get("candidate_fit")]
    assert fits, "expected at least one padded lexicon candidate"
    assert fits[0]["island_class"] in {"padded_lexicon", "code_switch_run", "passion_burst"}
    assert "myocardial" in (fits[0].get("evidence") or {}).get("island_text", "")


def test_scan_one_off_common_brick_not_candidate(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_one_off")
    words = [
        {"text": "This", "start_ms": 0, "end_ms": 200, "speaker_id": "spk_00", "confidence": 0.95},
        {"text": "is", "start_ms": 200, "end_ms": 300, "speaker_id": "spk_00", "confidence": 0.95},
        {"text": "just", "start_ms": 300, "end_ms": 500, "speaker_id": "spk_00", "confidence": 0.95},
        {"text": "the", "start_ms": 500, "end_ms": 700, "speaker_id": "spk_00", "confidence": 0.95},
        {"text": "same", "start_ms": 700, "end_ms": 900, "speaker_id": "spk_00", "confidence": 0.2},
        {"text": "thing", "start_ms": 900, "end_ms": 1200, "speaker_id": "spk_00", "confidence": 0.95},
        {"text": "again", "start_ms": 1200, "end_ms": 1500, "speaker_id": "spk_00", "confidence": 0.95},
    ]
    ctx.write_json("transcript/full.json", {"words": words})
    ctx.write_json(
        "segments/manifest.json",
        {"segments": [_seg("seg_1", start_ms=0, end_ms=1500, text="This is just the same thing again")]},
    )
    doc = scan_stt_lexicon_groups(ctx)
    fits = [g for g in doc["groups"] if g.get("candidate_fit")]
    assert fits == []
    skipped = [g for g in doc["groups"] if g.get("skip_reason") == "one_off_common_brick"]
    assert skipped


def test_scan_writes_nonfit_rows(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_nonfit")
    words = [
        {"text": "Hello", "start_ms": 0, "end_ms": 300, "speaker_id": "spk_00", "confidence": 0.98},
        {"text": "friends", "start_ms": 300, "end_ms": 700, "speaker_id": "spk_00", "confidence": 0.97},
    ]
    ctx.write_json("transcript/full.json", {"words": words})
    ctx.write_json(
        "segments/manifest.json",
        {"segments": [_seg("seg_clean", start_ms=0, end_ms=700, text="Hello friends")]},
    )
    doc = scan_stt_lexicon_groups(ctx)
    assert doc["groups"]
    assert all(not g.get("candidate_fit") for g in doc["groups"])
    assert any(g.get("skip_reason") == "no_low_conf_island" for g in doc["groups"])


def test_parent_siblings_code_switch_group(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_sibs")
    ctx.write_json("transcript/full.json", {"words": []})
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                _seg(
                    "seg_050a",
                    start_ms=0,
                    end_ms=2000,
                    parent_segment_id="seg_050",
                    audio_tags={"is_special": True},
                    retention="must_keep",
                ),
                _seg(
                    "seg_050b",
                    start_ms=2000,
                    end_ms=4000,
                    parent_segment_id="seg_050",
                    audio_tags={"is_special": False},
                ),
                _seg(
                    "seg_050c",
                    start_ms=4000,
                    end_ms=6000,
                    parent_segment_id="seg_050",
                    audio_tags={"is_special": True},
                    retention="must_keep",
                ),
            ]
        },
    )
    doc = scan_stt_lexicon_groups(ctx)
    sibs = [g for g in doc["groups"] if g.get("group_kind") == "parent_siblings" and g.get("candidate_fit")]
    assert sibs
    assert sibs[0]["island_class"] == "code_switch_run"
    assert "seg_050a" in sibs[0]["segment_ids"]


def test_build_priors_boost_only_no_negative(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_priors")
    ctx.write_json(
        ISLANDS_PATH,
        {
            "version": 1,
            "groups": [
                {
                    "group_id": "grp_014",
                    "segment_ids": ["seg_042"],
                    "sibling_segment_ids": [],
                    "island_class": "padded_lexicon",
                    "candidate_fit": True,
                    "evidence": {"probes": {}},
                }
            ],
        },
    )
    doc = build_stt_trust_priors(
        ctx,
        verdicts=[
            {
                "group_id": "grp_014",
                "segment_ids": ["seg_042"],
                "fits_case": True,
                "importance_score": 0.84,
                "boost_recommended": True,
                "failure_mode": "domain_lexicon",
                "rationale": "pads carry dosage claim",
            },
            {
                "group_id": "grp_015",
                "segment_ids": ["seg_043"],
                "fits_case": False,
                "importance_score": 0.2,
                "boost_recommended": False,
                "failure_mode": "noise",
                "rationale": "filler",
            },
        ],
    )
    assert ctx.artifact_exists(BOOSTS_PATH)
    sids = {p["segment_id"] for p in doc["priors"]}
    assert "seg_042" in sids
    assert "seg_043" not in sids
    assert all(float(p["soft_boost"]) > 0 for p in doc["priors"])


def test_passion_multiplier_raises_soft_boost(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_passion")
    ctx.write_json(
        ISLANDS_PATH,
        {
            "groups": [
                {
                    "group_id": "grp_1",
                    "segment_ids": ["seg_a"],
                    "island_class": "passion_burst",
                    "evidence": {"probes": {"passion_level": "high"}},
                }
            ]
        },
    )
    hot = build_stt_trust_priors(
        ctx,
        verdicts=[
            {
                "group_id": "grp_1",
                "segment_ids": ["seg_a"],
                "fits_case": True,
                "importance_score": 0.8,
                "boost_recommended": True,
                "failure_mode": "passion",
                "rationale": "emotional beat",
            }
        ],
    )
    ctx.write_json(
        ISLANDS_PATH,
        {
            "groups": [
                {
                    "group_id": "grp_1",
                    "segment_ids": ["seg_a"],
                    "island_class": "padded_lexicon",
                    "evidence": {"probes": {}},
                }
            ]
        },
    )
    base = build_stt_trust_priors(
        ctx,
        verdicts=[
            {
                "group_id": "grp_1",
                "segment_ids": ["seg_a"],
                "fits_case": True,
                "importance_score": 0.8,
                "boost_recommended": True,
                "failure_mode": "domain_lexicon",
                "rationale": "definition",
            }
        ],
    )
    assert float(hot["priors"][0]["soft_boost"]) > float(base["priors"][0]["soft_boost"])


def test_exclude_guard_restores_stt_noise_drop(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_guard")
    ctx.write_json(
        BOOSTS_PATH,
        {
            "priors": [
                {
                    "segment_id": "seg_042",
                    "soft_boost": 0.2,
                    "importance_score": 0.84,
                    "reasons": ["domain_lexicon"],
                    "group_ids": ["grp_014"],
                }
            ],
            "boosts": [
                {
                    "group_id": "grp_014",
                    "segment_ids": ["seg_042"],
                    "sibling_segment_ids": [],
                    "soft_boost": 0.2,
                    "importance_score": 0.84,
                }
            ],
        },
    )
    selection = {
        "ordered_segment_ids": ["seg_001"],
        "excluded_segment_ids": [
            {"segment_id": "seg_042", "reason": "low_quality STT failure"},
            {"segment_id": "seg_099", "reason": "aside"},
        ],
    }
    out = enforce_stt_island_selection_guards(ctx, selection)
    assert "seg_042" in out["ordered_segment_ids"]
    excl_ids = {
        (e.get("segment_id") if isinstance(e, dict) else e)
        for e in out["excluded_segment_ids"]
    }
    assert "seg_042" not in excl_ids
    assert "seg_099" in excl_ids


def test_sibling_cohesion_adds_special_sibling(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_cohesion")
    ctx.write_json(
        BOOSTS_PATH,
        {
            "priors": [
                {"segment_id": "seg_050a", "soft_boost": 0.2, "importance_score": 0.8, "group_ids": ["g1"]},
                {"segment_id": "seg_050c", "soft_boost": 0.2, "importance_score": 0.8, "group_ids": ["g1"]},
            ],
            "boosts": [
                {
                    "group_id": "g1",
                    "segment_ids": ["seg_050a", "seg_050c"],
                    "sibling_segment_ids": ["seg_050a", "seg_050c"],
                    "soft_boost": 0.2,
                    "importance_score": 0.8,
                }
            ],
        },
    )
    selection = {
        "ordered_segment_ids": ["seg_050a"],
        "excluded_segment_ids": [{"segment_id": "seg_050c", "reason": "low_quality"}],
    }
    out = enforce_stt_island_selection_guards(ctx, selection)
    assert "seg_050c" in out["ordered_segment_ids"]


def test_soft_protect_ids(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_protect")
    ctx.write_json(
        BOOSTS_PATH,
        {
            "priors": [
                {"segment_id": "seg_a", "soft_boost": 0.2, "importance_score": 0.9},
                {"segment_id": "seg_b", "soft_boost": 0.01, "importance_score": 0.2},
            ]
        },
    )
    ids = soft_protect_segment_ids(ctx)
    assert "seg_a" in ids
    assert "seg_b" not in ids


def test_specialist_registered():
    from interview_mux.llm_specialists import PRE_STAGE_SPECIALISTS, SPECIALIST_PROMPTS
    from interview_mux.openai_structured_output import SPECIALIST_SCHEMA_FILES
    from interview_mux.llm_interaction_registry import SPECIALIST_IDS

    assert "stt_lexicon_island_verify" in SPECIALIST_PROMPTS
    assert "stt_lexicon_island_verify" in SPECIALIST_SCHEMA_FILES
    assert SPECIALIST_IDS["stt_lexicon_island_verify"] == "OS-04"
    assert "stt_lexicon_island_verify" in PRE_STAGE_SPECIALISTS["full_master_ranking"]
