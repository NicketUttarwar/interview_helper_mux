"""Prior native segment context for synthetic gap VO (Plan 1)."""

from __future__ import annotations

import pytest

from interview_mux.artifact_repairs import repair_gap_report
from interview_mux.gap_vo_prior_context import (
    apply_prior_context_to_density_seed,
    attach_prior_native_contexts_to_payload,
    build_prior_context_volley_turns,
    build_prior_native_context,
    courtesy_seed_text,
    is_interruptive_opener,
    next_substantive_target,
)
from interview_mux import config as config_mod
from run_fixtures import isolated_run_ctx


def _seg(
    segment_id: str,
    *,
    start_ms: int,
    end_ms: int,
    text: str,
) -> dict:
    return {
        "segment_id": segment_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "speaker_id": "spk_0",
        "speaker_role": "interviewee",
        "type": "interviewee_answer",
        "text": text,
        "topic_tags": [],
        "flags": [],
    }


def _write_manifest(ctx) -> None:
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
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
                _seg(
                    "seg_003",
                    start_ms=94140,
                    end_ms=94860,
                    text="Okay.",
                ),
                _seg(
                    "seg_004",
                    start_ms=94860,
                    end_ms=120000,
                    text=(
                        "Because everything was put back into the company. But those were limited "
                        "resources and we could do only so much in that."
                    ),
                ),
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_002", "seg_003", "seg_004"],
            "chapters": [
                {
                    "title": "Founding Sparks & Early Cash Crunch",
                    "segment_ids": ["seg_002", "seg_003", "seg_004"],
                }
            ],
        },
        skip_handoff=True,
    )


def test_bhamb_mumbai_prior_is_impact_beat(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "prior_impact")
    _write_manifest(ctx)
    ordered = ["seg_002", "seg_003", "seg_004"]
    man = ctx.read_json("segments/manifest.json")
    by_id = {str(s["segment_id"]): s for s in man["segments"]}
    prior = build_prior_native_context(
        target_segment_id="seg_003",
        ordered_ids=ordered,
        segments_by_id=by_id,
        chapters=[{"title": "Founding", "segment_ids": ordered}],
    )
    assert prior is not None
    assert prior["segment_id"] == "seg_002"
    assert prior["prior_impact_beat"] is True
    assert prior["prior_complete_thought"] is True
    assert "Mumbai" in (prior.get("quote_span") or prior.get("end_window_text") or "")


def test_relocate_micro_okay_to_seg_004(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "prior_micro")
    _write_manifest(ctx)
    man = ctx.read_json("segments/manifest.json")
    by_id = {str(s["segment_id"]): s for s in man["segments"]}
    relocated = next_substantive_target(
        preferred_id="seg_003",
        ordered_ids=["seg_002", "seg_003", "seg_004"],
        segments_by_id=by_id,
    )
    assert relocated == "seg_004"


def test_density_seed_rewrites_interruptive_after_impact(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "prior_density")
    _write_manifest(ctx)
    stock = "Let me pause you there — what was the turning point in that stretch?"
    assert is_interruptive_opener(stock)
    sid, text, prior, prov = apply_prior_context_to_density_seed(
        ctx,
        target_segment_id="seg_003",
        category="framing_question",
        text=stock,
    )
    assert sid == "seg_004"  # relocated off Okay.
    assert prior is not None
    assert prior["prior_impact_beat"] is True
    assert not is_interruptive_opener(text)
    assert "pause you there" not in text.lower()
    assert prov.get("prior_segment_id") == "seg_002"
    assert prov.get("prior_impact_beat") is True


def test_courtesy_seed_after_impact() -> None:
    prior = {
        "prior_impact_beat": True,
        "prior_complete_thought": True,
        "quote_span": "the cash in our Bham account was higher than cash in our Mumbai account.",
    }
    text = courtesy_seed_text(
        prior,
        category="framing_question",
        target_segment_id="seg_167",
    )
    assert not is_interruptive_opener(text)
    assert "pause you there" not in text.lower()
    assert "167" not in text
    assert "seg_" not in text.lower()


def test_attach_prior_contexts_and_volley_turns(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "prior_volley")
    _write_manifest(ctx)
    payload = attach_prior_native_contexts_to_payload(ctx, {"segments": {}})
    assert "prior_native_contexts" in payload
    assert "seg_003" in payload["prior_native_contexts"]
    assert payload["prior_native_contexts"]["seg_003"]["prior_impact_beat"] is True
    assert payload["prior_native_context_policy"]["forbid_interruptive_openers_after_impact"] is True
    turns = build_prior_context_volley_turns(payload)
    assert len(turns) == 3
    assert turns[0]["role"] == "user"
    assert turns[1]["role"] == "assistant"
    assert "PRIOR NATIVE" in turns[0]["content"]


def test_repair_gap_report_density_courtesy(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "prior_repair")
    _write_manifest(ctx)
    monkeypatch.setattr(
        config_mod,
        "merged_config",
        lambda: {
            "analysis": {
                "gap_framing": {
                    "min_vo_insert_ratio": 0.5,
                    "prior_native_context": {"enabled": True, "rewrite_density_seeds": True},
                }
            }
        },
    )
    doc = {"interviewer_lines": []}
    repaired, applied = repair_gap_report(ctx, doc)
    lines = repaired.get("interviewer_lines") or []
    assert any(str(a.get("action") or "").startswith("seed_vo_density") for a in applied)
    for line in lines:
        assert "Let me pause you there" not in str(line.get("text") or "")
        if line.get("prior_impact_beat"):
            assert not is_interruptive_opener(str(line.get("text") or ""))
    if ctx.artifact_exists("understanding/gap_vo_context_audit.json"):
        audit = ctx.read_json("understanding/gap_vo_context_audit.json")
        assert isinstance(audit, dict)
        assert audit.get("lines")


def test_attach_vo_partner_context_includes_targets_and_missions(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.gap_vo_prior_context import attach_vo_partner_context_to_payload

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "vo_partner")
    _write_manifest(ctx)
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_004",
                    "self_explanatory": False,
                    "gap_type": "missing_setup",
                    "severity": "high",
                    "listener_confusion": "Listener lacks stakes before the limited-resources beat.",
                    "recommended_framing": "question",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/talking_points.json",
        {
            "strategy_summary": "Cash crunch arc",
            "through_line": "Resources",
            "talking_points": [
                {
                    "talking_point_id": "tp_cash",
                    "title": "Cash in Bham vs Mumbai",
                    "importance": "must_keep",
                    "why_it_matters": "Core impact",
                }
            ],
        },
        skip_handoff=True,
    )
    payload = attach_vo_partner_context_to_payload(ctx, {})
    assert "target_native_contexts" in payload
    assert "seg_004" in payload["target_native_contexts"]
    assert "limited" in payload["target_native_contexts"]["seg_004"]["text"].lower()
    assert payload["vo_missions"]["seg_004"]["mission"]
    assert "talking_points" in payload
    assert payload["vo_partner_policy"]["never_restate_next_clip"] is True


def test_vo_value_gate_allows_moderate_overlap_under_075() -> None:
    """Soft ceiling 0.75 allows intentional setup that shares some tokens."""
    from interview_mux.gap_vo_prior_context import vo_target_overlap_ratio, vo_value_violations

    target = (
        "Because everything was put back into the company. But those were limited "
        "resources and we could do only so much in that."
    )
    # Partial thematic overlap, not near-verbatim restatement.
    soft = {
        "line_id": "vo_soft",
        "targets_segment_id": "seg_004",
        "line_category": "story_bridge",
        "text": "With limited resources on the table, what did the company choose next?",
        "rationale": "Cue stakes without restating the full proof.",
    }
    segs = {"seg_004": {"segment_id": "seg_004", "text": target}}
    ratio = vo_target_overlap_ratio(str(soft["text"]), target)
    assert ratio < 0.75
    errs = vo_value_violations([soft], segments_by_id=segs)
    assert not any("restates next clip" in e for e in errs)


def test_vo_value_gate_flags_restate_and_missing_rationale() -> None:
    from interview_mux.gap_vo_prior_context import vo_value_violations

    target = (
        "Because everything was put back into the company. But those were limited "
        "resources and we could do only so much in that."
    )
    segs = {"seg_004": {"segment_id": "seg_004", "text": target}}
    restating = {
        "line_id": "vo_bad",
        "targets_segment_id": "seg_004",
        "line_category": "story_bridge",
        "text": (
            "Because everything was put back into the company but those were limited "
            "resources and we could do only so much in that."
        ),
        "rationale": "bridge",
    }
    good = {
        "line_id": "vo_good",
        "targets_segment_id": "seg_004",
        "line_category": "framing_question",
        "text": "What forced that cash crunch to become the turning point?",
        "rationale": "Unlock stakes before the limited-resources proof.",
    }
    missing = {
        "line_id": "vo_norat",
        "targets_segment_id": "seg_004",
        "line_category": "framing_question",
        "text": "What came next for the team after that moment?",
        "rationale": "",
    }
    errs = vo_value_violations([restating, good, missing], segments_by_id=segs)
    assert any("restates next clip" in e for e in errs)
    assert any("missing rationale" in e for e in errs)
    assert not any("vo_good" in e for e in errs)
