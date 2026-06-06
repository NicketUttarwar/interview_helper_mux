"""Centralized mocks for external APIs — deterministic offline test responses."""

from __future__ import annotations

import json
import wave
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from interview_mux.local_volley_framer import LocalFramingResult

_FIXTURES = Path(__file__).parent / "fixtures" / "prompts" / "stage_artifacts.json"
_STAGE_ARTIFACTS: dict[str, Any] | None = None


def load_stage_artifacts() -> dict[str, Any]:
    global _STAGE_ARTIFACTS
    if _STAGE_ARTIFACTS is None:
        _STAGE_ARTIFACTS = json.loads(_FIXTURES.read_text(encoding="utf-8"))
    return _STAGE_ARTIFACTS


def minimal_wav_bytes(*, duration_s: float = 0.25, sample_rate: int = 16000) -> bytes:
    n_frames = max(1, int(sample_rate * duration_s))
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


def simulated_llm_envelope(stage_key: str) -> dict[str, Any]:
    artifacts = load_stage_artifacts()
    artifact = artifacts.get(stage_key, {"status": "stub"})
    return {
        "status": "complete",
        "needs": [],
        "reasoning_summary": f"Simulated response for {stage_key}",
        "artifacts": artifact if isinstance(artifact, dict) else {"payload": artifact},
    }


def simulated_llm_json(stage_key: str) -> str:
    return json.dumps(simulated_llm_envelope(stage_key))


def _fake_openai_client(stage_key: str = "generic") -> MagicMock:
    captured: dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        msg = MagicMock()
        msg.content = simulated_llm_json(stage_key)
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    client = MagicMock()
    client.chat.completions.create = fake_create
    client._captured = captured
    return client


def _fake_aws_run(*args: str, **kwargs: Any) -> MagicMock:
    cmd = list(args)
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = "{}"
    proc.stderr = ""
    if "get-transcription-job" in cmd:
        proc.stdout = json.dumps(
            {
                "TranscriptionJob": {
                    "TranscriptionJobStatus": "COMPLETED",
                    "Transcript": {"TranscriptFileUri": "s3://bucket/out.json"},
                }
            }
        )
    elif "transcribe" in cmd and "start-transcription-job" in cmd:
        proc.stdout = ""
    elif "s3" in cmd and "cp" in cmd and len(cmd) >= 4:
        dest = cmd[-1]
        if dest.endswith("aws_raw.json"):
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_text(
                json.dumps(
                    {
                        "results": {
                            "transcripts": [{"transcript": "simulated transcript"}],
                            "items": [],
                            "speaker_labels": {"segments": []},
                        }
                    }
                ),
                encoding="utf-8",
            )
    return proc


def _fake_local_framer(*_args: Any, **_kwargs: Any) -> LocalFramingResult:
    return LocalFramingResult(
        escalate=False,
        confidence=0.9,
        reason="simulated_local_ok",
        volley_turns=[{"role": "assistant", "content": "Simulated local volley framing."}],
        used_local=True,
        model_id="simulated-model",
        latency_ms=1,
        tokens_approx=10,
        volley_turn_count=1,
    )


def apply_simulated_services(monkeypatch: pytest.MonkeyPatch, *, stage_key: str = "generic") -> None:
    """Wire OpenAI, AWS CLI, ElevenLabs REST, and local MLX mocks."""
    from interview_mux.stages import llm_runner

    client = _fake_openai_client(stage_key)
    monkeypatch.setattr(llm_runner, "OpenAI", lambda **_: client)
    monkeypatch.setattr(llm_runner, "require_secret", lambda _k: "sk-test-simulated")

    monkeypatch.setattr(
        "interview_mux.stages.transcribe_aws.subprocess.run",
        _fake_aws_run,
    )
    monkeypatch.setattr(
        "interview_mux.stages.transcribe_aws._aws",
        _fake_aws_run,
    )

    monkeypatch.setattr(
        "interview_mux.elevenlabs_rest._post_json_audio",
        lambda **_k: minimal_wav_bytes(),
    )
    monkeypatch.setattr(
        "interview_mux.elevenlabs_rest._request_bytes",
        lambda *_a, **_k: minimal_wav_bytes(),
    )

    monkeypatch.setattr(
        "interview_mux.local_volley_framer.frame_volley_with_local",
        _fake_local_framer,
    )
    monkeypatch.setattr(
        "interview_mux.local_volley_framer.mlx_available",
        lambda: True,
    )
