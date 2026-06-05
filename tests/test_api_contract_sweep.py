"""Lightweight GET/POST smoke for all documented /api/* routes (simulated run dir)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interview_mux.web.server import create_app
from run_fixtures import (
    grant_all_api_consents,
    init_run_meta_for_test,
    minimal_source_acoustic_profile,
    patch_executions_root,
    patch_server_ctx,
    seed_analysis_complete,
)
from simulated_services import apply_simulated_services, minimal_wav_bytes


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, str]:
    patch_executions_root(monkeypatch, tmp_path)
    apply_simulated_services(monkeypatch)

    run_id = "exec_api_sweep"
    fixture = Path(__file__).parent / "fixtures" / "runs" / "base_smoke"
    run_dir = tmp_path / "ASSETS" / "executions" / run_id
    shutil.copytree(fixture, run_dir)

    from interview_mux.run_context import RunContext

    ctx = RunContext(run_id, create=False)
    init_run_meta_for_test(ctx)
    source_wav = ctx.path("source_input.wav")
    source_wav.write_bytes(minimal_wav_bytes())
    meta = ctx.read_json("run_meta.json")
    meta["input_audio_path"] = str(source_wav.resolve())
    ctx.write_json("run_meta.json", meta)
    seed_analysis_complete(ctx)
    ctx.write_json("understanding/source_acoustic_profile.json", minimal_source_acoustic_profile())
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "type": "interviewer_question",
                    "speaker_id": "spk_001",
                    "speaker_role": "interviewer",
                    "topic_tags": ["origin_story"],
                    "start_ms": 0,
                    "end_ms": 5000,
                }
            ]
        },
    )
    ctx.write_json(
        "sound_design/elevenlabs_prompts.json",
        {
            "prompts": [
                {
                    "asset_id": "sting_a",
                    "elevenlabs_prompt": "Warm sting.",
                    "duration_seconds": 1.5,
                    "negative_prompt": "speech",
                }
            ]
        },
    )
    ingest = ctx.path("ingest")
    ingest.mkdir(parents=True, exist_ok=True)
    (ingest / "normalized.wav").write_bytes(minimal_wav_bytes())

    patch_server_ctx(monkeypatch, ctx)
    client = TestClient(create_app())
    grant_all_api_consents(client)
    return client, run_id


GET_ROUTES = [
    ("/api/health", {}, {"status"}),
    ("/api/config", {}, {"web_port"}),
    ("/api/session/api-consent", {}, {"providers"}),
    ("/api/session", {}, {"server"}),
    ("/api/assets", {}, {"files"}),
    ("/api/runs", {}, {"runs"}),
]


def test_global_get_routes(api_client: tuple[TestClient, str]) -> None:
    client, _run_id = api_client
    for path, params, keys in GET_ROUTES:
        res = client.get(path, params=params)
        assert res.status_code == 200, f"{path}: {res.text}"
        body = res.json()
        for key in keys:
            assert key in body, f"{path} missing {key}"


def test_run_get_routes(api_client: tuple[TestClient, str]) -> None:
    client, run_id = api_client
    routes: list[tuple[str, dict, set[str]]] = [
        (f"/api/runs/{run_id}/summary", {}, {"run_id"}),
        (f"/api/runs/{run_id}", {}, {"stages"}),
        (f"/api/runs/{run_id}/log", {"tail": 50}, {"entries"}),
        (f"/api/runs/{run_id}/timeline", {}, {"segments"}),
        (f"/api/runs/{run_id}/assembly-timeline", {}, {"ready"}),
        (f"/api/runs/{run_id}/waveform", {"path": "ingest/normalized.wav"}, {"peaks"}),
        (f"/api/runs/{run_id}/nle", {}, {}),
        (f"/api/runs/{run_id}/llm-routing", {}, {}),
        (f"/api/runs/{run_id}/llm-calls", {}, {"call_count"}),
        (f"/api/runs/{run_id}/job", {}, {"status"}),
        (f"/api/runs/{run_id}/transcript-review", {}, {"ready"}),
        (f"/api/runs/{run_id}/analysis-profile", {}, {"analysis_state"}),
        (f"/api/runs/{run_id}/story-board", {}, {}),
        (f"/api/runs/{run_id}/audio-quality", {}, {}),
        (f"/api/runs/{run_id}/elevenlabs-prompts", {}, {"prompts"}),
        (f"/api/runs/{run_id}/stages/transcribe/reuse-offers", {}, {"eligible"}),
        (f"/api/runs/{run_id}/artifact", {"path": "run_meta.json"}, {"execution_id"}),
        (f"/api/runs/{run_id}/audio", {"path": "ingest/normalized.wav"}, {}),
        (f"/api/runs/{run_id}/source-audio", {}, {}),
    ]
    for path, params, keys in routes:
        res = client.get(path, params=params)
        assert res.status_code == 200, f"{path}: {res.text}"
        if keys:
            body = res.json()
            for key in keys:
                assert key in body, f"{path} missing {key}"
        elif path.endswith("/audio") or path.endswith("/source-audio"):
            assert res.headers.get("content-type", "").startswith("audio/") or "octet" in res.headers.get(
                "content-type", ""
            )


def test_run_post_put_safe_routes(api_client: tuple[TestClient, str]) -> None:
    client, run_id = api_client

    assert client.post(f"/api/runs/{run_id}/log", json={"message": "sweep note", "level": "info"}).status_code == 200
    assert client.post(f"/api/runs/{run_id}/flow", json={"flow": "flow1"}).status_code == 200
    assert client.post(
        f"/api/runs/{run_id}/handoff-ack", json={"stage_id": "speaker_roles"}
    ).status_code == 200
    assert client.put("/api/session/active", json={"run_id": run_id}).status_code == 200
    assert client.post(
        f"/api/runs/{run_id}/preclean-offer",
        json={"checkpoint": "before_ingest", "action": "dismiss"},
    ).status_code == 200
    assert client.patch(
        f"/api/runs/{run_id}/acoustic-profile/overrides",
        json={"overrides": {"pace_class": "conversational"}},
    ).status_code == 200
    assert client.put(
        f"/api/runs/{run_id}/nle",
        json={"data": {"segment_overrides": {}, "segment_order": []}},
    ).status_code == 200
    assert client.post(
        f"/api/runs/{run_id}/nle/snap-boundary",
        json={"segment_id": "seg_001", "ms": 1200, "edge": "end"},
    ).status_code == 200
    assert client.post(
        f"/api/runs/{run_id}/milestones/preview-listened",
    ).status_code == 200

    review = client.get(f"/api/runs/{run_id}/transcript-review").json()
    chunks = review.get("chunks") or []
    if chunks:
        chunk_id = chunks[0].get("chunk_id") or chunks[0].get("id")
        if chunk_id:
            assert client.put(
                f"/api/runs/{run_id}/transcript-review/{chunk_id}",
                json={"text": "Corrected transcript text.", "reviewed": True},
            ).status_code == 200

    state = client.get(f"/api/runs/{run_id}/analysis-profile").json()["analysis_state"]
    assert client.put(
        f"/api/runs/{run_id}/analysis-profile",
        json={"data": state, "operator_verified": True},
    ).status_code == 200
    assert client.post(f"/api/runs/{run_id}/analysis-profile/verify").status_code == 200

    assert client.post(
        f"/api/runs/{run_id}/vo/line_001",
        files={"file": ("line_001.wav", minimal_wav_bytes(), "audio/wav")},
    ).status_code == 200

    prompts = client.get(f"/api/runs/{run_id}/elevenlabs-prompts").json()
    assert client.put(
        f"/api/runs/{run_id}/elevenlabs-prompts",
        json={"path": "sound_design/elevenlabs_prompts.json", "data": prompts},
    ).status_code == 200

    assert client.post(
        f"/api/runs/{run_id}/stages/transcribe/reuse",
        json={"action": "decline"},
    ).status_code == 200

    meta = client.get(f"/api/runs/{run_id}/artifact", params={"path": "run_meta.json"}).json()
    assert isinstance(meta, dict)
    assert meta.get("execution_id") == run_id
