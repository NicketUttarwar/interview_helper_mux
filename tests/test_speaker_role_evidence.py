"""Speaker-role evidence and tape-conflict lint (no S2S TTS)."""

from __future__ import annotations

from interview_mux.prompt_validation import validate_stage_artifacts
from interview_mux.speaker_role_evidence import (
    build_speaker_role_evidence,
    dominant_roles_from_talk_stats,
    fallback_speakers_artifact,
    is_unfulfillable_diarization_need,
    lint_role_tape_conflicts,
    persist_mixed_diarization_fallback,
    repair_role_tape_segment_types,
)
from run_fixtures import isolated_run_ctx, minimal_manifest_segment


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


def test_unfulfillable_diarization_need() -> None:
    assert is_unfulfillable_diarization_need(
        {"type": "rerun_stage", "stage": "diarization", "blocking": True}
    )
    assert is_unfulfillable_diarization_need(
        {"type": "rerun_stage", "stage": "speaker_diarization", "blocking": True}
    )
    assert is_unfulfillable_diarization_need(
        {"type": "rerun_stage", "stage": "transcribe", "blocking": True}
    )
    assert not is_unfulfillable_diarization_need(
        {"type": "operator", "stage": "diarization", "blocking": False}
    )
    assert not is_unfulfillable_diarization_need(
        {"type": "rerun_stage", "stage": "content_context", "blocking": True}
    )


def test_dominant_roles_longest_speaker_is_not_interviewer() -> None:
    roles = dominant_roles_from_talk_stats(
        [
            {
                "speaker_id": "spk_0",
                "talk_ms": 120_000,
                "question_count": 4,
                "turn_count": 20,
                "avg_turn_ms": 6000,
            },
            {
                "speaker_id": "spk_1",
                "talk_ms": 30_000,
                "question_count": 12,
                "turn_count": 18,
                "avg_turn_ms": 1600,
            },
        ]
    )
    by_id = {r["speaker_id"]: r for r in roles}
    assert by_id["spk_0"]["role"] == "interviewee"
    assert by_id["spk_0"]["narrative_function"] == "storyteller"
    assert by_id["spk_1"]["role"] == "interviewer"
    assert by_id["spk_1"]["narrative_function"] == "frame"


def test_fallback_speakers_artifact_validates() -> None:
    """SR-B2: mixed-diarization fallback is a schema-valid Full-auto honesty path."""
    artifact = fallback_speakers_artifact(
        [
            {"speaker_id": "spk_0", "talk_ms": 90_000, "question_count": 2, "turn_count": 10},
            {"speaker_id": "spk_1", "talk_ms": 20_000, "question_count": 8, "turn_count": 12},
        ]
    )
    assert artifact is not None
    assert not validate_stage_artifacts("speaker_roles", artifact)


def test_speaker_roles_contract_spine_is_soft_not_hard() -> None:
    """SR-B1: interview_spine must not be a hard PRESTAGE gate."""
    from interview_mux.stage_contract import load_contract

    contract = load_contract("speaker_roles")
    assert contract is not None
    hard = {d.path for d in contract.inputs if d.hard and d.path}
    soft = {d.path for d in contract.inputs if not d.hard and d.path}
    assert "transcript/full.json" in hard
    assert "understanding/interview_spine.json" not in hard
    assert "understanding/interview_spine.json" in soft


def test_persist_mixed_diarization_fallback_writes_speakers(tmp_path) -> None:
    import json

    ctx = isolated_run_ctx(tmp_path, "mixed_diar_fallback")
    words = []
    t = 0
    for _ in range(80):
        words.append({"speaker": "spk_0", "word": "story", "start_ms": t, "end_ms": t + 400})
        t += 450
    for _ in range(12):
        words.append({"speaker": "spk_1", "word": "why?", "start_ms": t, "end_ms": t + 200})
        t += 250
    (ctx.run_dir / "transcript").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "transcript" / "full.json").write_text(
        json.dumps({"text": "dialogue", "words": words}),
        encoding="utf-8",
    )
    (ctx.run_dir / "transcript" / "speakers.json").write_text(
        json.dumps({"speakers": [{"speaker_id": "spk_0"}, {"speaker_id": "spk_1"}]}),
        encoding="utf-8",
    )
    written = persist_mixed_diarization_fallback(ctx)
    assert written == ["understanding/speakers.json"]
    assert ctx.is_done("speaker_roles")
    doc = ctx.read_json("understanding/speakers.json")
    by_id = {s["speaker_id"]: s["role"] for s in doc["speakers"]}
    assert by_id["spk_0"] == "interviewee"
    assert by_id["spk_1"] == "interviewer"


def test_repair_role_tape_segment_types_clears_dense_conflicts(tmp_path) -> None:
    guest = _words(45)
    segs = [
        minimal_manifest_segment(
            f"seg_{i:03d}",
            start_ms=i * 5000,
            end_ms=(i + 1) * 5000,
            type="interviewer_question",
            text=guest,
        )
        for i in range(4)
    ]
    segs.append(
        minimal_manifest_segment(
            "seg_004",
            start_ms=20_000,
            end_ms=25_000,
            type="interviewee_answer",
            text=_words(50),
        )
    )
    ctx = isolated_run_ctx(tmp_path, "role_tape_repair")
    ctx.write_json("segments/manifest.json", {"segments": segs}, stage_key="segment_classification")
    applied = repair_role_tape_segment_types(ctx)
    assert len(applied) == 4
    manifest = ctx.read_json("segments/manifest.json")
    lint = lint_role_tape_conflicts(manifest)
    assert lint["blocking"] is False
