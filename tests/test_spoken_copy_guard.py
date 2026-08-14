from __future__ import annotations

import wave
from pathlib import Path
import sys

from interview_mux.spoken_copy_guard import (
    _grounded_fallback,
    dedupe_sentences,
    guard_spoken_copy,
    normalize_script,
    shorten_spoken_text,
    spoken_copy_violations,
)
from interview_mux.stages.assembly import resolve_vo_pickup_path
from interview_mux.vo_synthesis_audit import (
    record_synthesis,
    synthesis_entry_matches_line,
)
from run_fixtures import isolated_run_ctx, patch_merged_config

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import s2s_generate  # noqa: E402


def _wav(path: Path, duration_ms: int = 300) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 48_000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * duration_ms / 1000))


def test_topic_fallback_precedes_relative_question() -> None:
    decision = guard_spoken_copy(
        "Meanwhile—",
        evidence={
            "before_topic": "fundraising constraints",
            "after_topic": "the strategic sale",
            "before_excerpt": "We could not fund the campaign.",
            "after_excerpt": "The buyer approached us.",
            "source_gap_ms": 2000,
        },
        required=True,
        purpose="transition",
    )
    assert decision["action"] == "fallback"
    assert decision["text"] == (
        "Moving from fundraising constraints to the strategic sale, what changed?"
    )


def test_unsafe_topic_label_is_not_spoken() -> None:
    decision = guard_spoken_copy(
        "Meanwhile—",
        evidence={
            "before_topic": "segments/seg_12.json",
            "after_topic": "QC failure",
        },
        required=True,
        purpose="transition",
    )
    assert decision["action"] == "block"
    assert decision["text"] == ""


def test_nonchronological_next_phrase_is_blocked_without_topics() -> None:
    decision = guard_spoken_copy(
        "What happened next?",
        evidence={
            "before_excerpt": "The company was sold.",
            "after_excerpt": "Years earlier, the first product shipped.",
            "source_gap_ms": -120_000,
        },
        required=True,
        purpose="transition",
    )
    assert decision["action"] == "block"
    assert "spoken_generic_filler" in decision["violations"] or "spoken_stock_copy" in decision["violations"]


def test_editorial_filler_without_context_fails_closed() -> None:
    decision = guard_spoken_copy(
        "There is more to that story.",
        evidence={},
        required=True,
        purpose="transition",
    )
    assert decision["action"] == "block"
    assert "spoken_generic_filler" in decision["violations"] or "spoken_stock_copy" in decision["violations"]


def test_edit_structure_and_chapter_language_are_rejected() -> None:
    for text in (
        "In the previous clip, gym buyers showed up.",
        "The earlier segment ended on snack demand.",
        "Turning to the next segment, what changed?",
        "Welcome to this chapter of the story.",
        "Chapter Four opens on ownership.",
        "As we discussed earlier on the show.",
    ):
        hits = spoken_copy_violations(text, evidence={})
        assert hits, f"expected violations for {text!r}"
        assert any(
            h.startswith("spoken_")
            and (
                "chapter" in h
                or "edit_structure" in h
                or "scaffold" in h
                or "construction" in h
            )
            for h in hits
        ), hits


def test_contextual_english_without_edit_structure_is_allowed() -> None:
    text = (
        "After the gym-buyer beat, protein-aware snacking rewrote the market. "
        "What nearly broke the supply chain?"
    )
    assert spoken_copy_violations(text, evidence={}) == []
    assert spoken_copy_violations(
        "A segment of the market preferred the protein bar.",
        evidence={},
    ) == []
    assert "spoken_production_jargon" not in spoken_copy_violations(
        "On the timeline of his career, the choice was clear.",
        evidence={},
    )


def test_repeated_copy_and_next_clip_restatement_are_rejected() -> None:
    text = "The buyer approached after months of difficult negotiation."
    violations = spoken_copy_violations(
        text,
        evidence={
            "target_excerpt": (
                "After months of difficult negotiation, the buyer approached the company."
            )
        },
        seen_texts=[text],
    )
    assert "spoken_repeated_copy" in violations
    assert "spoken_next_clip_restatement" in violations


def test_repeated_sentence_is_rejected_within_or_across_vo_lines() -> None:
    repeated_in_line = spoken_copy_violations(
        "What changed after the deal? What changed after the deal?",
        evidence={},
    )
    assert "spoken_repeated_sentence_in_line" in repeated_in_line

    repeated_across_lines = spoken_copy_violations(
        "What changed after the deal? Why did it matter?",
        evidence={},
        seen_texts=["What changed after the deal?"],
    )
    assert "spoken_repeated_sentence" in repeated_across_lines


def test_assert_guarded_loads_sibling_seen_texts(tmp_path) -> None:
    from interview_mux.spoken_copy_guard import (
        assert_guarded_spoken_copy,
        load_persisted_spoken_texts,
        sentence_keys,
    )

    ctx = isolated_run_ctx(tmp_path, "run_seen_siblings")
    sibling = "Protein buyers rewrote the addressable market."
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_a",
                    "gap_type": "missing_setup",
                    "text": sibling,
                    "targets_segment_id": "seg_1",
                    "placement": "before",
                    "delivery": "synthesize",
                }
            ]
        },
        skip_handoff=True,
    )
    loaded = load_persisted_spoken_texts(ctx, exclude_line_id="vo_b")
    assert sibling in loaded
    colliding = f"{sibling} What broke next?"
    # No topic evidence → cannot fallback; must block before TTS.
    try:
        assert_guarded_spoken_copy(
            colliding,
            evidence={},
            purpose="vo[vo_b]",
            ctx=ctx,
            exclude_line_id="vo_b",
        )
        raise AssertionError("expected sibling sentence collision to raise")
    except ValueError as exc:
        assert "spoken_repeated_sentence" in str(exc)
    # With topic evidence, fallback may rewrite — but never keep the colliding key.
    decision = assert_guarded_spoken_copy(
        colliding,
        evidence={"before_topic": "snack pivot", "after_topic": "supply cliff"},
        purpose="vo[vo_b]",
        ctx=ctx,
        exclude_line_id="vo_b",
    )
    assert not (set(sentence_keys(decision["text"])) & set(sentence_keys(sibling)))


def test_orientation_keep_rejects_structure_hits() -> None:
    decision = guard_spoken_copy(
        "In this chapter, a founder explains the sale to Zydus Wellness.",
        evidence={"strict_grounding": True, "target_excerpt": "Asha founded Acme."},
        required=True,
        purpose="vo[vo_preface_episode_orientation]",
    )
    assert decision["action"] in {"block", "fallback", "omit"}
    assert not decision.get("kept_orientation")


def test_dedupe_sentences_keeps_the_final_question_form() -> None:
    assert dedupe_sentences(
        "Why did the founder sell? Why did the founder sell?"
    ) == "Why did the founder sell?"


def test_fragment_safe_shortening() -> None:
    text = "This sentence is complete. This second sentence would be cut badly."
    assert shorten_spoken_text(text, 5) == "This sentence is complete."
    assert not shorten_spoken_text("one two three four five", 3).endswith("…")


def test_paths_placeholders_and_unsupported_names_are_rejected() -> None:
    violations = spoken_copy_violations(
        "Open artifacts/seg_12.json and introduce Mallory from {company}.",
        evidence={"strict_grounding": True, "target_excerpt": "Asha founded Acme."},
    )
    assert "spoken_path_or_filename" in violations
    assert "spoken_placeholder" in violations
    assert any(v.startswith("spoken_unsupported_entity") for v in violations)


def test_discourse_markers_are_not_unsupported_entities() -> None:
    violations = spoken_copy_violations(
        "Alright, what changed after the team locked the deal?",
        evidence={
            "strict_grounding": True,
            "before_excerpt": "the team locked the deal",
            "after_excerpt": "what came next for the brand",
            "before_topic": "deal close",
            "after_topic": "brand next steps",
        },
    )
    assert not any(v.startswith("spoken_unsupported_entity") for v in violations)


def test_required_orientation_keeps_preface_despite_unsupported_entities() -> None:
    preface = (
        "In this conversation, a founder explains how consumer insight, "
        "disciplined profitable growth, and a commitment to sharing value "
        "with employees led him to sell Right Bite to Zydus Wellness."
    )
    decision = guard_spoken_copy(
        preface,
        evidence={"strict_grounding": True, "target_excerpt": "Asha founded Acme."},
        required=True,
        purpose="vo[vo_preface_episode_orientation]",
    )
    assert decision["text"] == normalize_script(preface)
    assert decision.get("kept_orientation") is True
    assert "How did" not in decision["text"]
    assert "Zydus" in decision["text"]


def test_grounded_fallback_skips_clause_as_person() -> None:
    text = _grounded_fallback(
        {
            "verified_person": (
                "A founder explains how consumer insight, disciplined "
                "profitable growth, and a commitment"
            )
        }
    )
    assert "How did A founder explains" not in text


def test_stale_script_hash_rejects_generated_wav(
    tmp_path, monkeypatch
) -> None:
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "gap_vo": {
                    "post_synthesis_qc": {
                        "enabled": False,
                        "speech_qa_enabled": False,
                    }
                }
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "run_stale_vo")
    wav = ctx.path("vo_pickup", "synthesized", "line_1.wav")
    _wav(wav)
    original = {
        "line_id": "line_1",
        "text": "Protein buyers rewrote the addressable market.",
        "targets_segment_id": "seg_1",
        "placement": "before",
    }
    record_synthesis(ctx, original, backend="mlx_audio", out_wav=wav)
    changed = {**original, "text": "What made the deal possible?"}

    matches, reason = synthesis_entry_matches_line(ctx, changed)
    assert matches is False
    assert reason == "stale_script_hash"
    assert resolve_vo_pickup_path(ctx, changed) is None

    retargeted = {**original, "targets_segment_id": "seg_2"}
    matches, reason = synthesis_entry_matches_line(ctx, retargeted)
    assert matches is True
    assert reason == "script_match_stale_context"


def test_tone_mode_never_prefixes_delivery_instruction(
    tmp_path, monkeypatch
) -> None:
    ref = tmp_path / "ref.wav"
    out = tmp_path / "out.wav"
    _wav(ref)
    captured: dict[str, str] = {}

    def fake_run_tts(**kwargs):
        captured["text"] = kwargs["text"]
        _wav(kwargs["out_wav"])

    monkeypatch.setattr(s2s_generate, "_run_tts", fake_run_tts)
    s2s_generate.run_payload(
        {
            "mode": "tone",
            "model_id": "dummy",
            "text": "The listener hears only this.",
            "ref_audio": str(ref),
            "out_wav": str(out),
            "tone": "analytical",
        }
    )
    assert captured["text"] == "The listener hears only this."


def test_early_stage_is_not_production_jargon() -> None:
    text = (
        "Vijay contrasts boom-time deal flow with today's drought — "
        "from a hundred early-stage deals down to maybe twenty."
    )
    assert "spoken_production_jargon" not in spoken_copy_violations(text, evidence={})
    assert "spoken_production_jargon" not in spoken_copy_violations(
        "How the founder’s life stage shaped the decision.",
        evidence={},
    )
    assert "spoken_production_jargon" not in spoken_copy_violations(
        "On the timeline of his career, the choice was clear.",
        evidence={},
    )
    assert "spoken_production_jargon" in spoken_copy_violations(
        "The pipeline stage failed QC", evidence={}
    )


def test_edl_raises_on_duplicate_spoken_sentence(tmp_path) -> None:
    from interview_mux.stages.assembly import _gap_lines_for_segment

    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_1",
                "targets_segment_id": "seg_a",
                "placement": "before",
                "delivery": "synthesize",
                "text": "Protein buyers rewrote the market.",
            },
            {
                "line_id": "vo_2",
                "targets_segment_id": "seg_b",
                "placement": "before",
                "delivery": "synthesize",
                "text": "Protein buyers rewrote the market. What broke next?",
            },
        ]
    }
    seen: set[str] = set()
    first = _gap_lines_for_segment(
        gap, "seg_a", "before", emitted_sentence_keys=seen
    )
    assert len(first) == 1
    try:
        _gap_lines_for_segment(gap, "seg_b", "before", emitted_sentence_keys=seen)
        raise AssertionError("expected duplicate sentence to raise")
    except ValueError as exc:
        assert "duplicate spoken sentence" in str(exc)

