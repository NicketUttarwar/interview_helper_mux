"""Speaker-role evidence and tape-conflict lint (no S2S TTS)."""

from __future__ import annotations

from interview_mux.speaker_role_evidence import (
    build_speaker_role_evidence,
    lint_role_tape_conflicts,
)


def _words(n: int) -> str:
    return " ".join(["story"] * n)


def test_build_speaker_role_evidence_includes_pair_verdicts() -> None:
    ev = build_speaker_role_evidence(
        {
            "speakers": [{"speaker_id": "spk_0"}, {"speaker_id": "spk_1"}],
            "transcript_samples": [
                {"speaker_id": "spk_0", "text": "Can you walk me through the origin?"},
                {"speaker_id": "spk_1", "text": "We started in a small town and grew from there."},
            ],
            "diarization_repairs": {
                "pairs": [
                    {
                        "from_speaker_id": "spk_1",
                        "to_speaker_id": "spk_0",
                        "verdict": "yes_same",
                    },
                    {
                        "from_speaker_id": "spk_0",
                        "to_speaker_id": "spk_1",
                        "verdict": "no_different",
                    },
                ]
            },
        }
    )
    assert ev["diarization_pair_verdicts"][0]["same_speaker"] is True
    assert ev["diarization_pair_verdicts"][1]["same_speaker"] is False
    assert any("Sortformer" in h for h in ev["role_evidence_hints"])


def test_lint_role_tape_conflicts_blocks_when_dense() -> None:
    guest = _words(45)
    host_q = "Can you tell me what changed?"
    segs = []
    for i in range(4):
        segs.append(
            {
                "segment_id": f"seg_{i:03d}",
                "type": "interviewer_question",
                "text": guest,
            }
        )
    segs.append({"segment_id": "seg_004", "type": "interviewee_answer", "text": host_q})
    segs.append({"segment_id": "seg_005", "type": "interviewee_answer", "text": _words(50)})
    lint = lint_role_tape_conflicts({"segments": segs})
    assert lint["blocking"] is True
    assert lint["conflict_count"] >= 4


def test_lint_role_tape_conflicts_ignores_sparse_mismatches() -> None:
    segs = [
        {
            "segment_id": "seg_001",
            "type": "interviewer_question",
            "text": "What happened next?",
        },
        {
            "segment_id": "seg_002",
            "type": "interviewee_answer",
            "text": _words(50),
        },
        {
            "segment_id": "seg_003",
            "type": "interviewer_question",
            "text": _words(45),
        },
    ]
    lint = lint_role_tape_conflicts({"segments": segs})
    assert lint["blocking"] is False
    assert lint["conflict_count"] == 1
