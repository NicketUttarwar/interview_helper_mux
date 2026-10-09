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


def test_stt_period_on_fragment_is_hanging_setup() -> None:
    from interview_mux.gap_vo_prior_context import (
        clause_continues_after,
        ends_complete_thought,
        ends_hanging_setup,
        is_legal_conceptual_hinge,
    )

    hanging = (
        "So early prediction of a reoccurrence, if I could do through cell biopsy."
    )
    complete = "Okay. Then I think we have conquered the big thing."
    assert ends_hanging_setup(hanging)
    assert not ends_complete_thought(hanging)
    assert not is_legal_conceptual_hinge(hanging, next_pause_ms=700)
    assert not ends_hanging_setup(complete)
    assert ends_complete_thought(complete)

    words = []
    t = 0
    for tok in hanging.split():
        words.append({"text": tok, "speaker_id": "spk_0", "start_ms": t, "end_ms": t + 180})
        t += 200
    cut = words[-1]["end_ms"]
    t = cut + 700
    for tok in complete.split():
        words.append({"text": tok, "speaker_id": "spk_1", "start_ms": t, "end_ms": t + 180})
        t += 200
    assert clause_continues_after(words, cut)
    assert not is_legal_conceptual_hinge(hanging, words=words, end_ms=cut, next_pause_ms=700)


def _novel_1080_words(*, gap_ms: int, later_speaker: str = "spk_0") -> tuple[list[dict], int]:
    left = "we have developed a very novel".split()
    right = "1080 gene panel that works".split()
    words: list[dict] = []
    t = 0
    for tok in left:
        words.append({"text": tok, "speaker_id": "spk_1", "start_ms": t, "end_ms": t + 180})
        t += 200
    cut = words[-1]["end_ms"]
    t = cut + gap_ms
    for tok in right:
        words.append({"text": tok, "speaker_id": later_speaker, "start_ms": t, "end_ms": t + 180})
        t += 200
    return words, cut


def test_unfinished_nominal_novel_is_hang_not_evaluative_close() -> None:
    from interview_mux.gap_vo_prior_context import (
        ends_complete_thought,
        ends_hanging_setup,
        ends_unfinished_nominal,
        is_legal_conceptual_hinge,
    )

    hang = "we have developed a very novel"
    assert ends_unfinished_nominal(hang)
    assert ends_hanging_setup(hang)
    assert not ends_complete_thought(hang, next_pause_ms=1120)
    assert not is_legal_conceptual_hinge(hang, next_pause_ms=1120)
    assert not ends_hanging_setup("that's novel")
    assert not ends_unfinished_nominal("that's novel")
    assert not ends_hanging_setup("really powerful")
    assert not ends_unfinished_nominal("really powerful")
    assert ends_complete_thought("that's novel", next_pause_ms=1120)


def test_novel_1080_continues_inside_thirty_seconds() -> None:
    from interview_mux.gap_vo_prior_context import (
        CONCEPT_EDGE_MS,
        clause_continues_after,
        is_legal_conceptual_hinge,
    )

    close = "we have developed a very novel"
    for gap in (1120, 3900):
        words, cut = _novel_1080_words(gap_ms=gap)
        assert clause_continues_after(words, cut), gap
        assert not is_legal_conceptual_hinge(close, words=words, end_ms=cut, next_pause_ms=gap)
    for gap in (4100, 20_000):
        words, cut = _novel_1080_words(gap_ms=gap)
        assert clause_continues_after(words, cut, max_lookahead_ms=CONCEPT_EDGE_MS), gap
        assert not is_legal_conceptual_hinge(close, words=words, end_ms=cut, next_pause_ms=gap)

    words, cut = _novel_1080_words(gap_ms=31_000)
    assert not clause_continues_after(words, cut, max_lookahead_ms=CONCEPT_EDGE_MS)
    # Still not a legal hinge: unfinished nominal even when lookahead misses the complement.
    assert not is_legal_conceptual_hinge(close, words=words, end_ms=cut, next_pause_ms=31_000)

    # Non-hang close + 4.1s pause is a real split.
    done = "the treatment is ready"
    t = 0
    words = []
    for tok in done.split():
        words.append({"text": tok, "speaker_id": "spk_1", "start_ms": t, "end_ms": t + 180})
        t += 200
    cut = words[-1]["end_ms"]
    t = cut + 4100
    words.append({"text": "Next", "speaker_id": "spk_1", "start_ms": t, "end_ms": t + 180})
    assert not clause_continues_after(words, cut)
    assert is_legal_conceptual_hinge(done, words=words, end_ms=cut, next_pause_ms=4100)


def _reshape_clinical_words() -> tuple[list[dict], dict[str, int]]:
    """exec_1649-class span: abutting clinical|trials, then list close, then CTA."""
    specs = [
        ("reshape", 94040, 94480, "spk_1"),
        ("clinical", 94480, 94820, "spk_1"),
        ("trials,", 94820, 95460, "spk_1"),
        ("drug", 96160, 96300, "spk_0"),
        ("development,", 96300, 96780, "spk_0"),
        ("and", 96780, 97120, "spk_0"),
        ("diagnostics.", 97120, 97920, "spk_0"),
        ("Well,", 97920, 98320, "spk_0"),
        ("before", 98580, 98780, "spk_0"),
        ("we", 98780, 99000, "spk_0"),
        ("begin,", 99000, 99220, "spk_0"),
    ]
    words = [
        {"text": t, "start_ms": s, "end_ms": e, "speaker_id": spk}
        for t, s, e, spk in specs
    ]
    marks = {row[0].rstrip(",."): row[2] for row in specs}
    marks["clinical"] = 94820
    marks["trials"] = 95460
    marks["diagnostics"] = 97920
    return words, marks


def test_abutting_clinical_trials_is_not_a_hinge() -> None:
    from interview_mux.gap_vo_prior_context import (
        clause_continues_after,
        end_is_hanging_clause,
        is_legal_conceptual_hinge,
    )

    words, marks = _reshape_clinical_words()
    clinical = marks["clinical"]
    assert clause_continues_after(words, clinical)
    assert end_is_hanging_clause(words, clinical)
    assert not is_legal_conceptual_hinge(
        "reshape clinical",
        words=words,
        end_ms=clinical,
        next_pause_ms=0,
    )
    assert clause_continues_after(words, marks["trials"])
    assert end_is_hanging_clause(words, marks["trials"])
    assert is_legal_conceptual_hinge(
        "reshape clinical trials, drug development, and diagnostics.",
        words=words,
        end_ms=marks["diagnostics"],
        next_pause_ms=0,
    )
    assert not clause_continues_after(words, marks["diagnostics"])


def _timed(tokens: list[str], *, start: int, speaker: str, gap_before: int = 0) -> tuple[list[dict], int]:
    words: list[dict] = []
    t = start + gap_before
    for tok in tokens:
        words.append({"text": tok, "speaker_id": speaker, "start_ms": t, "end_ms": t + 180})
        t += 220
    return words, words[-1]["end_ms"] if words else start


def test_say_what_inside_thirty_seconds_is_one_concept() -> None:
    """The continuation can sit well past a breath and still finish the same concept."""
    from interview_mux.gap_vo_prior_context import (
        CONCEPT_EDGE_MS,
        clause_continues_after,
        is_legal_conceptual_hinge,
    )

    left, cut = _timed("We looked at it. And to say.".split(), start=1_520_840, speaker="spk_1")
    right, _end = _timed(
        "What is the next thing. We build the business.".split(),
        start=cut,
        speaker="spk_0",
        gap_before=20_000,
    )
    words = left + right
    assert clause_continues_after(words, cut, max_lookahead_ms=CONCEPT_EDGE_MS)
    assert not is_legal_conceptual_hinge(
        "We looked at it. And to say.",
        words=words,
        end_ms=cut,
        next_pause_ms=20_000,
    )


def test_new_question_inside_thirty_seconds_still_cuts() -> None:
    from interview_mux.gap_vo_prior_context import is_legal_conceptual_hinge

    left, cut = _timed(
        "the company shipped the snack bar in june".split(),
        start=0,
        speaker="spk_0",
    )
    right, _end = _timed(
        "what happened after that launch".split(),
        start=cut,
        speaker="spk_1",
        gap_before=20_000,
    )
    words = left + right
    assert is_legal_conceptual_hinge(
        "the company shipped the snack bar in june",
        words=words,
        end_ms=cut,
        next_pause_ms=20_000,
    )


def test_say_what_we_build_is_one_concept() -> None:
    from interview_mux.gap_vo_prior_context import (
        clause_continues_after,
        is_legal_conceptual_hinge,
    )

    left, cut = _timed("We looked at it. And to say.".split(), start=0, speaker="spk_1")
    right, _end = _timed(
        "What is the next thing. We build the business.".split(),
        start=cut,
        speaker="spk_0",
        gap_before=1000,
    )
    words = left + right
    assert clause_continues_after(words, cut)
    assert not is_legal_conceptual_hinge(
        "We looked at it. And to say.",
        words=words,
        end_ms=cut,
        next_pause_ms=1000,
    )


def test_verb_without_object_stays_with_the_object() -> None:
    from interview_mux.gap_vo_prior_context import (
        concept_cut_allowed,
        next_starts_new_clause,
        sentence_still_flowing,
        verb_waiting_on_object,
    )

    assert verb_waiting_on_object("we build")
    assert not verb_waiting_on_object("we build the business")
    assert not verb_waiting_on_object("we shipped it.")
    assert not verb_waiting_on_object("That was it.")
    assert not next_starts_new_clause("the business in public")
    assert next_starts_new_clause("What happened after that")
    assert next_starts_new_clause("The treatment is ready")
    assert sentence_still_flowing("we build", "the business in public")
    assert sentence_still_flowing("we build", "the snack bar")
    assert not concept_cut_allowed("we build", "the business in public")
    assert not concept_cut_allowed("we build", "the snack bar")
    assert concept_cut_allowed("we build the business.", "What happened after that")
    assert concept_cut_allowed("we left.", "The company launched a product.")
    assert concept_cut_allowed("we agreed.", "The treatment is ready.")
    assert not sentence_still_flowing("we left.", "The company launched a product.")


def _words_at(pairs: list[tuple[str, int]]) -> list[dict]:
    out = []
    for text, start in pairs:
        out.append({"text": text, "start_ms": start, "end_ms": start + 180})
    return out


def test_forward_30s_investigation_reads_each_word() -> None:
    from interview_mux.gap_vo_prior_context import investigate_forward_cut

    words = _words_at(
        [
            ("we", 0),
            ("build", 200),
            ("the", 8_000),
            ("business", 8_200),
            ("in", 8_400),
            ("public.", 8_600),
            ("What", 20_000),
            ("happened", 20_200),
            ("after", 20_400),
            ("that", 20_600),
        ]
    )
    # The clock cut lands on the bare verb. The 30s pass moves it to the object.
    assert investigate_forward_cut(words, 380) == 8_780
    # A finished line in front of a new sentence stays put.
    left = _words_at(
        [
            ("we", 0),
            ("left.", 200),
            ("The", 5_000),
            ("company", 5_200),
            ("launched", 5_400),
            ("a", 5_600),
            ("product.", 5_800),
        ]
    )
    assert investigate_forward_cut(left, 380) == 380
    ready = _words_at(
        [
            ("the", 0),
            ("treatment", 200),
            ("is", 400),
            ("ready.", 600),
            ("Next", 4_700),
            ("chapter", 4_900),
            ("starts", 5_100),
        ]
    )
    assert investigate_forward_cut(ready, 780) == 780
    launches = _words_at(
        [
            ("we", 0),
            ("left.", 200),
            ("The", 5_000),
            ("company", 5_200),
            ("launches", 5_400),
            ("a", 5_600),
            ("product.", 5_800),
        ]
    )
    assert investigate_forward_cut(launches, 380) == 380
    joined = _words_at(
        [
            ("we", 0),
            ("left.", 200),
            ("and", 8_000),
            ("the", 8_200),
            ("company", 8_400),
            ("launched", 8_600),
            ("a", 8_800),
            ("product.", 9_000),
        ]
    )
    assert investigate_forward_cut(joined, 380) == 380
    longer = _words_at(
        [
            ("so", 0),
            ("today", 200),
            ("we", 400),
            ("build", 600),
            ("the", 8_000),
            ("business", 8_200),
            ("in", 8_400),
            ("public.", 8_600),
            ("What", 12_000),
            ("happened", 12_200),
        ]
    )
    assert investigate_forward_cut(longer, 780) == 8_780
    new_beat = _words_at(
        [
            ("we", 0),
            ("were", 200),
            ("going", 400),
            ("to", 600),
            ("So", 2_000),
            ("next", 2_200),
            ("question.", 2_400),
        ]
    )
    assert investigate_forward_cut(new_beat, 780) == 780


def test_keeper_air_bounds_use_the_30s_word_investigation() -> None:
    from interview_mux.ideal_cuts import resolve_keeper_air_bounds

    words = _words_at(
        [
            ("we", 0),
            ("build", 200),
            ("the", 8_000),
            ("business", 8_200),
            ("in", 8_400),
            ("public.", 8_600),
            ("What", 20_000),
            ("happened", 20_200),
        ]
    )
    meta: dict = {}
    _start, end = resolve_keeper_air_bounds(
        source_start_ms=0,
        source_end_ms=380,
        words=words,
        min_keep_ms=200,
        meta_out=meta,
    )
    # The concept closes on "public." The existing silence pad may add up to 1s.
    assert 8_780 <= end <= 8_780 + 1_000
    assert str(meta["air_bound_reason"]).startswith("forward_window_30s")
    assert end < 20_000


def test_parallel_platform_examples_stay_one_concept() -> None:
    from interview_mux.gap_vo_prior_context import (
        clause_continues_after,
        is_legal_conceptual_hinge,
    )

    left, cut = _timed(
        "We have granola. We have peanut butter.".split(),
        start=0,
        speaker="spk_0",
    )
    right, _end = _timed(
        "We have plant protein.".split(),
        start=cut,
        speaker="spk_0",
        gap_before=400,
    )
    words = left + right
    assert clause_continues_after(words, cut)
    assert not is_legal_conceptual_hinge(
        "We have granola. We have peanut butter.",
        words=words,
        end_ms=cut,
        next_pause_ms=400,
    )


def test_new_question_is_a_concept_cut_without_period_or_speaker_flip() -> None:
    from interview_mux.gap_vo_prior_context import is_legal_conceptual_hinge

    left, cut = _timed(
        "the company shipped the snack bar in june".split(),
        start=0,
        speaker="spk_0",
    )
    right, _end = _timed(
        "what happened after that launch".split(),
        start=cut,
        speaker="spk_0",
        gap_before=80,
    )
    words = left + right
    assert is_legal_conceptual_hinge(
        "the company shipped the snack bar in june",
        words=words,
        end_ms=cut,
        next_pause_ms=80,
    )


def test_tell_me_opens_a_new_question() -> None:
    from interview_mux.gap_vo_prior_context import is_legal_conceptual_hinge

    left, cut = _timed(
        "the company shipped the snack bar in june".split(),
        start=0,
        speaker="spk_0",
    )
    right, _end = _timed(
        "tell me about the factory".split(),
        start=cut,
        speaker="spk_1",
        gap_before=200,
    )
    words = left + right
    assert is_legal_conceptual_hinge(
        "the company shipped the snack bar in june",
        words=words,
        end_ms=cut,
        next_pause_ms=200,
    )


def test_walk_me_through_opens_a_new_question() -> None:
    from interview_mux.gap_vo_prior_context import is_legal_conceptual_hinge

    left, cut = _timed(
        "the company shipped the snack bar in june".split(),
        start=0,
        speaker="spk_0",
    )
    right, _end = _timed(
        "walk me through the factory".split(),
        start=cut,
        speaker="spk_1",
        gap_before=200,
    )
    words = left + right
    assert is_legal_conceptual_hinge(
        "the company shipped the snack bar in june",
        words=words,
        end_ms=cut,
        next_pause_ms=200,
    )


def test_and_opens_a_segment_only_for_a_new_thought() -> None:
    from interview_mux.gap_vo_prior_context import is_legal_conceptual_hinge

    left, cut = _timed(
        "the company shipped the snack bar in june".split(),
        start=0,
        speaker="spk_0",
    )
    same, _end = _timed(
        "and we have the peanut butter line".split(),
        start=cut,
        speaker="spk_0",
        gap_before=400,
    )
    assert not is_legal_conceptual_hinge(
        "the company shipped the snack bar in june",
        words=left + same,
        end_ms=cut,
        next_pause_ms=400,
    )
    new, _end = _timed(
        "and then we started a second company".split(),
        start=cut,
        speaker="spk_0",
        gap_before=400,
    )
    assert is_legal_conceptual_hinge(
        "the company shipped the snack bar in june",
        words=left + new,
        end_ms=cut,
        next_pause_ms=400,
    )


def test_density_drop_ranks_above_a_dense_concept_change() -> None:
    from interview_mux.gap_vo_prior_context import concept_boundary_rank

    dense = concept_boundary_rank(gap_ms=80, density_before=3.0, density_after=3.2)
    breath = concept_boundary_rank(gap_ms=1200, density_before=3.0, density_after=1.0)
    assert breath > dense
