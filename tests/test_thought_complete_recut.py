"""Thought-complete recut: traverse following speech, cut at the finished clause."""

from __future__ import annotations

from interview_mux.thought_complete_recut import (
    apply_thought_complete_to_clips,
    complete_thought_candidates,
    enrich_thought_complete_findings,
)
from interview_mux.order_hash import stamp_order_hash
from run_fixtures import isolated_run_ctx


def _words(*pairs: tuple[str, int, int], speaker: str = "spk_0") -> list[dict]:
    return [
        {"text": text, "start_ms": start, "end_ms": end, "speaker_id": speaker}
        for text, start, end in pairs
    ]


def test_candidates_cut_before_okay_not_the_next_section():
    words = _words(
        ("making", 0, 400),
        ("sense", 2100, 2400),
        ("out", 2400, 2600),
        ("of", 2600, 2750),
        ("it,", 2750, 3200),
        ("okay,", 3500, 3800),
        ("correlating", 3900, 4500),
        ("the", 4500, 4700),
        ("data.", 4700, 5200),
    )
    cuts = complete_thought_candidates(words, 400, horizon_ms=8000, speaker="spk_0")
    assert cuts
    assert cuts[0] == 3200
    assert all(ms <= 3800 for ms in cuts)


def test_candidates_stop_before_second_complete_idea():
    words = _words(
        ("if", 0, 400),
        ("we", 500, 700),
        ("never", 700, 900),
        ("shipped", 900, 1200),
        ("the", 1200, 1400),
        ("release.", 1400, 1800),
        ("Then", 2200, 2500),
        ("we", 2500, 2700),
        ("went", 2700, 3000),
        ("to", 3000, 3200),
        ("market", 3200, 3600),
        ("later.", 3600, 4000),
    )
    cuts = complete_thought_candidates(words, 400, horizon_ms=5000, speaker="spk_0")
    assert cuts == [1800]


def test_candidates_cross_speaker_list_closes_at_diagnostics():
    words = [
        {"text": "clinical", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_1"},
        {"text": "trials,", "start_ms": 400, "end_ms": 900, "speaker_id": "spk_1"},
        {"text": "drug", "start_ms": 1600, "end_ms": 1900, "speaker_id": "spk_0"},
        {"text": "development,", "start_ms": 1900, "end_ms": 2400, "speaker_id": "spk_0"},
        {"text": "and", "start_ms": 2400, "end_ms": 2600, "speaker_id": "spk_0"},
        {"text": "diagnostics.", "start_ms": 2600, "end_ms": 3200, "speaker_id": "spk_0"},
        {"text": "Well,", "start_ms": 3200, "end_ms": 3600, "speaker_id": "spk_0"},
        {"text": "subscribe", "start_ms": 4000, "end_ms": 4500, "speaker_id": "spk_0"},
    ]
    cuts = complete_thought_candidates(words, 400, horizon_ms=8000, speaker="")
    assert cuts
    assert cuts[0] == 3200


def test_apply_extends_hanging_and_leaves_leftover_independent():
    clips = [
        {
            "type": "speech",
            "segment_id": "seg_a",
            "source_start_ms": 0,
            "source_end_ms": 400,
            "timeline_start_ms": 0,
            "duration_ms": 400,
        },
        {
            "type": "speech",
            "segment_id": "seg_b",
            "source_start_ms": 3500,
            "source_end_ms": 8000,
            "timeline_start_ms": 400,
            "duration_ms": 4500,
        },
    ]
    finding = {
        "segment_id": "seg_a",
        "kind": "incomplete_clause",
        "action": "thought_complete_recut",
        "detail": {
            "keep_end_ms": 3200,
            "remainder_start_ms": 3500,
            "consumed_segment_ids": [],
        },
    }
    out, overrides, changed = apply_thought_complete_to_clips(
        clips, finding, overrides={}, excluded=set(), exclude_reasons={}
    )
    assert changed
    by_id = {c["segment_id"]: c for c in out}
    assert by_id["seg_a"]["source_end_ms"] == 3200
    assert by_id["seg_b"]["source_start_ms"] == 3500
    assert by_id["seg_b"]["source_end_ms"] == 8000
    assert "seg_b" not in overrides or not overrides.get("seg_b", {}).get("excluded")


def test_enrich_uses_batched_llm_keep_end(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_thought_llm")
    segments = [
        {
            "segment_id": "seg_a",
            "start_ms": 0,
            "end_ms": 400,
            "speaker_id": "spk_0",
            "speaker_role": "interviewee",
            "type": "interviewee_answer",
            "text": "making",
            "topic_tags": [],
            "flags": [],
        },
        {
            "segment_id": "seg_b",
            "start_ms": 3500,
            "end_ms": 8000,
            "speaker_id": "spk_0",
            "speaker_role": "interviewee",
            "type": "interviewee_answer",
            "text": "okay, correlating the data later.",
            "topic_tags": [],
            "flags": [],
        },
    ]
    words = [
        {"text": "making", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_0"},
        {"text": "sense", "start_ms": 2100, "end_ms": 2400, "speaker_id": "spk_0"},
        {"text": "out", "start_ms": 2400, "end_ms": 2600, "speaker_id": "spk_0"},
        {"text": "of", "start_ms": 2600, "end_ms": 2750, "speaker_id": "spk_0"},
        {"text": "it,", "start_ms": 2750, "end_ms": 3200, "speaker_id": "spk_0"},
        {"text": "okay,", "start_ms": 3500, "end_ms": 3800, "speaker_id": "spk_0"},
        {"text": "correlating", "start_ms": 3900, "end_ms": 4500, "speaker_id": "spk_0"},
        {"text": "the", "start_ms": 4500, "end_ms": 4700, "speaker_id": "spk_0"},
        {"text": "data", "start_ms": 4700, "end_ms": 5000, "speaker_id": "spk_0"},
        {"text": "later.", "start_ms": 5000, "end_ms": 5400, "speaker_id": "spk_0"},
    ]
    ctx.write_json("segments/manifest.json", {"segments": segments}, skip_handoff=True)
    ctx.write_json("transcript/full.json", {"words": words}, skip_handoff=True)
    ctx.write_json(
        "master/selection.json",
        stamp_order_hash({"ordered_segment_ids": ["seg_a", "seg_b"], "chapters": []}),
        skip_handoff=True,
    )
    edl = {
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 400,
            },
            {
                "type": "speech",
                "segment_id": "seg_b",
                "source_start_ms": 3500,
                "source_end_ms": 8000,
            },
        ]
    }

    def _fake_envelope(*_a, **_k):
        return {
            "status": "complete",
            "artifacts": {
                "junction_thought_complete": {
                    "version": 1,
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "cuts": [
                        {
                            "case_id": "seg_a",
                            "keep_end_ms": 3200,
                            "remainder_start_ms": 3500,
                            "rationale": "Finish making sense out of it, leave correlating independent.",
                        }
                    ],
                }
            },
        }

    monkeypatch.setattr(
        "interview_mux.stages.llm_runner.run_prompt_envelope",
        _fake_envelope,
    )
    findings = [
        {
            "segment_id": "seg_a",
            "clip_index": 0,
            "action": "thought_complete_recut",
            "kind": "incomplete_clause",
            "detail": {"end_text": "making"},
        }
    ]
    out, llm_calls = enrich_thought_complete_findings(ctx, edl, findings, allow_llm=True)
    assert llm_calls == 1
    detail = out[0].get("detail") or {}
    assert detail.get("cut_source") == "llm"
    assert int(detail["keep_end_ms"]) == 3200
    assert int(detail["remainder_start_ms"]) == 3500
    assert "correlating" in str(detail.get("rationale") or "").lower()
