"""Speaker roles partial persist must enrich talk stats before schema validation."""

from __future__ import annotations

import json
from unittest.mock import patch

from interview_mux.llm_output_resilience import apply_resilience_and_persist
from interview_mux.prompt_validation import validate_artifact_write
from run_fixtures import isolated_run_ctx


def _seed_transcript(run) -> None:
    (run / "transcript").mkdir(parents=True, exist_ok=True)
    words = []
    for speaker, count in (("spk_0", 40), ("spk_1", 35)):
        t = 0
        for _ in range(count):
            words.append(
                {
                    "speaker": speaker,
                    "word": "hello",
                    "start_ms": t,
                    "end_ms": t + 500,
                }
            )
            t += 600
    (run / "transcript" / "full.json").write_text(
        json.dumps({"text": "dialogue", "words": words}),
        encoding="utf-8",
    )
    (run / "transcript" / "speakers.json").write_text(
        json.dumps(
            {
                "speakers": [
                    {"id": "spk_0", "role": "unknown"},
                    {"id": "spk_1", "role": "unknown"},
                ]
            }
        ),
        encoding="utf-8",
    )


def test_speaker_roles_partial_persist_backfills_avg_turn_length(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "speaker_roles_persist")
    _seed_transcript(ctx.run_dir)

    envelope = {
        "status": "complete",
        "artifacts": {
            "speakers": [
                {
                    "speaker_id": "spk_0",
                    "role": "interviewer",
                    "confidence": 0.8,
                    "avg_turn_length_ms": None,
                },
                {
                    "speaker_id": "spk_1",
                    "role": "interviewee",
                    "confidence": 0.8,
                    "avg_turn_length_ms": None,
                },
            ],
        },
    }
    arbiter = {"verdict": "accept", "confidence": 0.9}

    with patch("interview_mux.write_staging.write_approval_enabled", return_value=True):
        plan = apply_resilience_and_persist(
            ctx,
            "speaker_roles",
            1,
            envelope,
            arbiter,
            [],
            [],
            persist_fn=lambda _c, _a: None,
        )

    assert plan.action in ("partial", "full"), plan.report.summary
    speakers = plan.artifacts.get("speakers") or []
    assert speakers[0]["avg_turn_length_ms"] is not None
    assert speakers[1]["avg_turn_length_ms"] is not None
    errors = validate_artifact_write("understanding/speakers.json", plan.artifacts)
    assert not errors, errors


def test_speaker_roles_partial_persist_omits_null_evidence_windows(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "speaker_roles_evidence_windows")
    _seed_transcript(ctx.run_dir)

    envelope = {
        "status": "complete",
        "artifacts": {
            "speakers": [
                {
                    "speaker_id": "spk_0",
                    "role": "interviewer",
                    "confidence": 0.8,
                    "evidence": ["asks questions"],
                    "evidence_windows": None,
                },
                {
                    "speaker_id": "spk_1",
                    "role": "interviewee",
                    "confidence": 0.8,
                    "evidence": ["answers questions"],
                    "evidence_windows": None,
                },
            ],
        },
    }
    arbiter = {"verdict": "accept", "confidence": 0.9}

    with patch("interview_mux.write_staging.write_approval_enabled", return_value=True):
        plan = apply_resilience_and_persist(
            ctx,
            "speaker_roles",
            1,
            envelope,
            arbiter,
            [],
            [],
            persist_fn=lambda _c, _a: None,
        )

    assert plan.action in ("partial", "full"), plan.report.summary
    speakers = plan.artifacts.get("speakers") or []
    assert all("evidence_windows" not in row for row in speakers)
    errors = validate_artifact_write("understanding/speakers.json", plan.artifacts)
    assert not errors, errors
