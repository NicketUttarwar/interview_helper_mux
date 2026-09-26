"""Hard-fix plan: must-keep, e2e_soft, spoken-copy, packet lint, runtime JSON."""

from __future__ import annotations

from typing import Any

from interview_mux.e2e_soft import e2e_soft_enabled
from interview_mux.hard_keep import enforce_hard_keeps, hard_keep_segment_ids
from interview_mux.local_runtime import classify_runtime_error, parse_runtime_json_stdout
from interview_mux.spoken_copy_guard import spoken_copy_violations
from interview_mux.volley_packet_lint import lint_llm_user_payload, strip_forbidden_metadata


class _FakeCtx:
    def __init__(self, store: dict[str, Any] | None = None):
        self._store = store or {}

    def artifact_exists(self, rel: str) -> bool:
        return rel in self._store

    def read_json(self, rel: str) -> Any:
        return self._store[rel]

    def log(self, *args: Any, **kwargs: Any) -> None:
        return None


def test_e2e_soft_default_off(monkeypatch):
    monkeypatch.delenv("INTERVIEW_MUX_E2E_SOFT", raising=False)
    assert e2e_soft_enabled(meta={"e2e_soft_listen_delight": True}) is False
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    assert e2e_soft_enabled(meta={"e2e_soft_listen_delight": True}) is True


def test_hard_keep_restores_vanish_from_both():
    ctx = _FakeCtx(
        {
            "understanding/ideal_cuts.json": {"must_keep_segment_ids": ["seg_keep"]},
            "understanding/talking_points.json": {
                "talking_points": [{"must_keep": True, "segment_id": "seg_tp"}]
            },
        }
    )
    keeps = hard_keep_segment_ids(ctx)
    assert "seg_keep" in keeps
    assert "seg_tp" in keeps
    out = enforce_hard_keeps(
        ctx,
        {
            "ordered_segment_ids": ["seg_other"],
            "excluded_segment_ids": [{"segment_id": "seg_keep", "reason": "aside"}],
        },
    )
    assert "seg_keep" in out["ordered_segment_ids"]
    assert "seg_tp" in out["ordered_segment_ids"]
    excl_ids = {
        (e.get("segment_id") if isinstance(e, dict) else e)
        for e in out["excluded_segment_ids"]
    }
    assert "seg_keep" not in excl_ids


def test_hard_keep_finale_tail_omits_early_chapter_instead_of_append():
    ctx = _FakeCtx(
        {
            "understanding/ideal_cuts.json": {"must_keep_segment_ids": ["seg_001"]},
            "master/narrative_plan.json": {
                "chapters": [
                    {"chapter_id": "ch_open", "segment_ids": ["seg_001", "seg_002"]},
                    {"chapter_id": "ch_coda", "segment_ids": ["seg_coda"]},
                ]
            },
        }
    )
    out = enforce_hard_keeps(
        ctx,
        {
            "ordered_segment_ids": ["seg_coda"],
            "excluded_segment_ids": [{"segment_id": "seg_001", "reason": "aside"}],
        },
    )
    assert "seg_001" not in out["ordered_segment_ids"]
    assert out["ordered_segment_ids"][-1] == "seg_coda"
    excl = out["excluded_segment_ids"]
    assert any(
        (isinstance(row, dict) and row.get("segment_id") == "seg_001" and row.get("reason") == "finale_tail_leftover")
        for row in excl
    )
    assert (out.get("exclude_rationales") or {}).get("seg_001") == "finale_tail_leftover"


def test_hard_keep_last_chapter_restores_before_letter_split_signoff():
    ctx = _FakeCtx(
        {
            "understanding/ideal_cuts.json": {
                "must_keep_segment_ids": ["seg_045", "seg_047", "seg_049", "seg_050"]
            },
            "segments/boundaries.json": {
                "boundaries": [
                    {"segment_id": "seg_044", "start_ms": 2_700_000},
                    {"segment_id": "seg_045", "start_ms": 2_792_660},
                    {"segment_id": "seg_047", "start_ms": 3_000_000},
                    {"segment_id": "seg_049", "start_ms": 3_100_000},
                    {"segment_id": "seg_050", "start_ms": 3_200_000},
                    {"segment_id": "seg_051", "start_ms": 3_374_470},
                ]
            },
            "master/narrative_plan.json": {
                "chapters": [
                    {
                        "chapter_id": "ch_trials",
                        "segment_ids": ["seg_051a", "seg_051i"],
                    },
                    {
                        "chapter_id": "ch_validation",
                        "segment_ids": ["seg_045", "seg_047", "seg_049", "seg_050"],
                    },
                ]
            },
        }
    )
    out = enforce_hard_keeps(
        ctx,
        {
            "ordered_segment_ids": ["seg_044", "seg_051a", "seg_051i"],
            "excluded_segment_ids": [
                {"segment_id": "seg_045", "reason": "aside"},
                {"segment_id": "seg_047", "reason": "aside"},
                {"segment_id": "seg_049", "reason": "aside"},
                {"segment_id": "seg_050", "reason": "aside"},
            ],
        },
    )
    order = out["ordered_segment_ids"]
    for sid in ("seg_045", "seg_047", "seg_049", "seg_050"):
        assert sid in order
        assert order.index(sid) < order.index("seg_051i")
    assert order[-1] == "seg_051i"


def test_spoken_copy_imperatives_not_entities():
    ev = {
        "strict_grounding": True,
        "target_excerpt": "Bham told a war story that stuck",
        "before_excerpt": "we kept going",
    }
    for line in (
        "Listen for the one that stuck",
        "Brace for his war-story",
        "Remember, Bham",
    ):
        errs = spoken_copy_violations(line, evidence=ev)
        assert not any(e.startswith("spoken_unsupported_entity") for e in errs), (line, errs)


def test_volley_lint_strips_metadata():
    cleaned = strip_forbidden_metadata(
        {
            "transcript": "hello from tape",
            "stage_done": True,
            "path_ok": True,
            "run_meta": {"e2e_soft": True},
            "nested": {"exists": True, "segment_text": "keep me"},
        }
    )
    assert "stage_done" not in cleaned
    assert "path_ok" not in cleaned
    assert "run_meta" not in cleaned
    assert cleaned["transcript"] == "hello from tape"
    assert "exists" not in cleaned["nested"]
    out = lint_llm_user_payload({"transcript": "x" * 50, "e2e_heal": True})
    assert "e2e_heal" not in out


def test_runtime_json_prefers_last_object_and_classifies():
    raw = "loading weights...\n{\"ok\": false, \"error\": \"missing voice ref\"}\n"
    parsed = parse_runtime_json_stdout(raw)
    assert parsed and parsed.get("ok") is False
    assert classify_runtime_error("missing voice reference wav", "") == "missing_voice_ref"
    assert classify_runtime_error("CUDA OOM", "") == "oom"


def test_pick_best_order_reports_dropped():
    from interview_mux.rank_candidates import pick_best_order

    pick = pick_best_order(
        [
            {"source": "a", "ordered_segment_ids": ["s1", "s2"]},
            {"source": "b", "ordered_segment_ids": ["s1", "s2", "s3"]},
        ]
    )
    assert "dropped_segment_ids" in pick
    assert set(pick["dropped_segment_ids"]) <= {"s1", "s2", "s3"}


def test_spoken_copy_entity_rewrite_before_omit():
    from interview_mux.spoken_copy_guard import guard_spoken_copy

    ev = {
        "strict_grounding": True,
        "target_excerpt": "the interview continued quietly",
        "before_excerpt": "the room went quiet",
    }
    decision = guard_spoken_copy(
        "Mallory kept the tape rolling",
        evidence=ev,
        required=False,
        purpose="test",
    )
    assert decision["action"] in {"fallback", "allow"}
    assert decision["text"]
    assert "Mallory" not in decision["text"]


def test_lint_require_tape_rejects_empty():
    import pytest

    with pytest.raises(ValueError, match="tape-derived"):
        lint_llm_user_payload({"exists": True, "stage_done": True}, require_tape=True)


def test_connector_fuse_defaults_incomplete_thought_only():
    from interview_mux.segment_fuse import _DEFAULTS

    assert _DEFAULTS["incomplete_thought_only"] is True
    assert _DEFAULTS["prefer_stay_when_uncertain"] is True
    assert _DEFAULTS["allow_high_value_bridge"] is False
    assert int(_DEFAULTS["max_fused_duration_ms"] or 0) == 25000
    assert int(_DEFAULTS["max_fused_members"] or 0) == 3
    # Finite fuse budget (hanging cuts still converge without unbounded thrash).
    assert int(_DEFAULTS["max_fuses_per_pass"] or 0) > 0
    assert int(_DEFAULTS["max_fuse_rounds"] or 0) > 0


def test_hard_keep_blank_exclude_beats_restore():
    """Lattice: blank_or_unusable exclude must not be restored by hard_keep."""
    ctx = _FakeCtx(
        {
            "understanding/ideal_cuts.json": {"must_keep_segment_ids": ["seg_blank"]},
            "master/selection.json": {
                "ordered_segment_ids": ["seg_other"],
                "excluded_segment_ids": [
                    {
                        "segment_id": "seg_blank",
                        "reason": "blank_or_unusable_answer_audio",
                    }
                ],
                "exclude_rationales": {
                    "seg_blank": "blank_or_unusable_answer_audio",
                },
            },
        }
    )
    keeps = hard_keep_segment_ids(ctx)
    assert "seg_blank" not in keeps
    out = enforce_hard_keeps(
        ctx,
        {
            "ordered_segment_ids": ["seg_other"],
            "excluded_segment_ids": [
                {
                    "segment_id": "seg_blank",
                    "reason": "blank_or_unusable_answer_audio",
                }
            ],
            "exclude_rationales": {"seg_blank": "blank_or_unusable_answer_audio"},
        },
    )
    assert "seg_blank" not in out["ordered_segment_ids"]


def test_hard_keep_drops_blank_excluded_segments():
    """Blank-excluded tape must leave hard_keep so post-commit lint can pass."""
    ctx = _FakeCtx(
        {
            "analysis/low_conf_must_keep.json": {
                "enforcement_mode": "authoritative",
                "must_keep_segment_ids": ["seg_024", "seg_057", "seg_025"],
            },
            "segments/manifest.json": {
                "segments": [
                    {
                        "segment_id": "seg_024",
                        "text": "Okay.",
                        "start_ms": 0,
                        "end_ms": 300,
                    },
                    {
                        "segment_id": "seg_057",
                        "text": "Thank you.",
                        "start_ms": 1000,
                        "end_ms": 1300,
                    },
                    {
                        "segment_id": "seg_025",
                        "text": "The assay rebuilt how we see living tumor biology in the clinic.",
                        "start_ms": 2000,
                        "end_ms": 12000,
                    },
                ]
            },
            "master/selection.json": {
                "ordered_segment_ids": ["seg_025"],
                "excluded_segment_ids": [
                    {"segment_id": "seg_024", "reason": "blank_or_unusable_answer_audio"},
                    {"segment_id": "seg_057", "reason": "blank_or_unusable_answer_audio"},
                ],
            },
        }
    )
    # authoritative_must_keep_ids reads analysis path — stub via ideal_cuts instead
    ctx._store["understanding/ideal_cuts.json"] = {
        "must_keep_segment_ids": ["seg_024", "seg_057", "seg_025"],
        "cuts": [{"segment_id": "seg_025", "must_keep": True}],
    }
    keeps = hard_keep_segment_ids(ctx)
    assert "seg_024" not in keeps
    assert "seg_057" not in keeps
    assert "seg_025" in keeps


def test_hard_keep_drops_orphan_ids_absent_from_manifest():
    """exec_11165: low-conf must-keep seg_069 not in manifest must not poison ranking."""
    ctx = _FakeCtx(
        {
            "understanding/ideal_cuts.json": {
                "must_keep_segment_ids": ["seg_022", "seg_069"],
                "cuts": [{"segment_id": "seg_022", "must_keep": True}],
            },
            "segments/manifest.json": {
                "segments": [
                    {
                        "segment_id": "seg_022",
                        "text": "Liquid biopsy changed monitoring.",
                        "start_ms": 0,
                        "end_ms": 4000,
                    },
                ]
            },
        }
    )
    keeps = hard_keep_segment_ids(ctx)
    assert "seg_022" in keeps
    assert "seg_069" not in keeps


def test_hard_keep_cta_parent_via_selection_exclude_without_cta_artifact():
    """CTA parent excluded in selection transfers keep to on-air children (no media_ip_cta.json)."""
    ctx = _FakeCtx(
        {
            "understanding/ideal_cuts.json": {
                "must_keep_segment_ids": ["seg_001"],
                "cuts": [{"segment_id": "seg_001", "must_keep": True}],
            },
            "segments/manifest.json": {
                "segments": [
                    {
                        "segment_id": "seg_001",
                        "text": "Please subscribe.",
                        "start_ms": 0,
                        "end_ms": 5000,
                    },
                    {
                        "segment_id": "seg_001c",
                        "text": (
                            "OneCell lets oncologists see living tumor biology "
                            "in the clinic before they choose a therapy path."
                        ),
                        "start_ms": 500,
                        "end_ms": 9000,
                        "parent_id": "seg_001",
                    },
                ]
            },
            "master/selection.json": {
                "ordered_segment_ids": ["seg_001c"],
                "excluded_segment_ids": [
                    {"segment_id": "seg_001", "reason": "media_ip_cta"}
                ],
            },
        }
    )
    keeps = hard_keep_segment_ids(ctx)
    assert "seg_001" not in keeps
    assert "seg_001c" in keeps


def test_hard_keep_does_not_transfer_to_cta_scrap_children():
    """Cascade (MUX_FORENSICS=0): sponsor-scrap NLE children do not inherit keep."""
    ctx = _FakeCtx(
        {
            "understanding/ideal_cuts.json": {
                "must_keep_segment_ids": ["seg_054"],
                "cuts": [{"segment_id": "seg_054", "must_keep": True}],
            },
            "segments/manifest.json": {
                "segments": [
                    {
                        "segment_id": "seg_054",
                        "text": "Thanks to our sponsor Agilisium Labs.",
                        "start_ms": 0,
                        "end_ms": 4000,
                    },
                    {
                        "segment_id": "seg_054cb",
                        "text": "sponsor, Agilisium Labs.",
                        "start_ms": 4000,
                        "end_ms": 5500,
                    },
                    {
                        "segment_id": "seg_053",
                        "text": "Diagnosis is much better than cure in this setting.",
                        "start_ms": 8000,
                        "end_ms": 14000,
                    },
                ]
            },
            "master/selection.json": {
                "ordered_segment_ids": ["seg_053", "seg_054cb"],
                "excluded_segment_ids": [
                    {"segment_id": "seg_054", "reason": "media_ip_cta"}
                ],
                "exclude_rationales": {"seg_054": "media_ip_cta"},
            },
        }
    )
    keeps = hard_keep_segment_ids(ctx)
    assert "seg_054" not in keeps
    assert "seg_054cb" not in keeps
