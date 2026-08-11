from __future__ import annotations

import wave
from pathlib import Path
import sys

from interview_mux.spoken_copy_guard import (
    guard_spoken_copy,
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


def test_nonchronological_next_phrase_is_repaired() -> None:
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
    assert decision["action"] == "fallback"
    assert decision["text"].startswith("Stepping back")


def test_editorial_filler_without_context_fails_closed() -> None:
    decision = guard_spoken_copy(
        "There is more to that story.",
        evidence={},
        required=True,
        purpose="transition",
    )
    assert decision["action"] == "block"
    assert "spoken_generic_filler" in decision["violations"]


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
        "text": "What changed after that?",
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
    assert "spoken_production_jargon" in spoken_copy_violations(
        "The pipeline stage failed QC", evidence={}
    )
