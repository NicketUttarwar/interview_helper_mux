from __future__ import annotations

from fastapi.testclient import TestClient

from interview_mux.api_providers import all_provider_grants
from interview_mux.run_context import RunContext
from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, patch_executions_root, patch_server_ctx


def test_session_api_consent_includes_auto_grants(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "interview_mux.web.server.load_persisted_consents",
        lambda: {},
    )
    client = TestClient(create_app())
    res = client.get("/api/session/api-consent")
    assert res.status_code == 200
    body = res.json()
    assert "openai" in {p["id"] for p in body["providers"]}
    assert body["grants"].get("openai") is True
    assert "aws" not in body["grants"]


def test_all_provider_grants_auto_true() -> None:
    grants = all_provider_grants()
    assert grants.get("openai") is True
    assert "aws" not in grants


def test_execute_not_blocked_by_consent(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_consent_20260101T001100Z", create=True)
    init_run_meta_for_test(ctx)
    # Delivery/analysis preflight for speaker_roles needs tape + prepare outputs.
    wav = ctx.path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 64)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "fixture tape for consent execute",
            "words": [
                {"text": "fixture", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_0"},
                {"text": "tape", "start_ms": 400, "end_ms": 800, "speaker_id": "spk_0"},
            ],
            "segments": [],
        },
        skip_handoff=True,
    )
    spine = ctx.final_path("understanding", "interview_spine.json")
    spine.parent.mkdir(parents=True, exist_ok=True)
    spine.write_text(
        '{"schema_version":1,"derived_from":[],"encoders":{},"window_policy":{},'
        '"windows":[],"boundary_events":[],"retrieval":{}}',
        encoding="utf-8",
    )
    for sid in (
        "audio_preclean",
        "ingest",
        "transcribe",
        "transcript_review_build",
        "audio_probe_build",
        "source_acoustic_profile",
        "interview_spine_build",
    ):
        done = ctx.final_path(".stage_done", sid)
        done.parent.mkdir(parents=True, exist_ok=True)
        done.write_text("done\n", encoding="utf-8")
    patch_server_ctx(monkeypatch, ctx)

    from interview_mux.config import merged_config

    if not str((merged_config().get("secrets") or {}).get("OPENAI_API_KEY") or "").strip():
        import pytest

        pytest.skip(
            "no OPENAI_API_KEY configured: the server then reports "
            "needs_api_consent for missing credentials, which this test cannot "
            "distinguish from consent actually blocking execution"
        )
    client = TestClient(create_app())
    res = client.post(
        f"/api/runs/{ctx.run_id}/execute",
        json={"mode": "stage", "stage": "speaker_roles", "api_consents": {}},
    )
    # Consent must not block; later preflight/runtime gaps may still 500.
    if res.status_code == 200:
        payload = res.json()
        assert not payload.get("needs_api_consent")
    else:
        assert "consent" not in (res.text or "").lower()
