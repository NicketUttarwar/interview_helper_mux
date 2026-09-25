"""TBIY Flow 1 operator journey — API integration (topology → story → G1 → preview → G1.5 → SFX gate)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interview_mux.gates_tbiy import check_g1_5_preview_pickup_pending, require_g1_5_preview_pickup_clear
from interview_mux.production_profile import TBIY_STYLE, is_tbiy
from interview_mux.run_context import RunContext
from interview_mux.web.server import create_app, mark_preview_listened
from run_fixtures import (
    MINIMAL_WAV_BYTES,
    confirm_test_pickup_speaker,
    init_run_meta_for_test,
    mark_done_raw,
    minimal_content_brief,
    minimal_gap_line,
    minimal_gap_report,
    minimal_manifest,
    patch_executions_root,
    populated_analysis_state,
    seed_flow1_sound_spend_ready,
    write_fixture_json,
    write_fixture_theme_wav,
)

_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "tbiy" / "one_on_one_asymmetric"

def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURE_ROOT / name).read_text(encoding="utf-8"))

def seed_tbiy_journey_ctx(ctx: RunContext) -> None:
    """Seed a run at post-analyze / pre-ship with TBIY profile artifacts."""
    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    ctx.path("segments").mkdir(parents=True, exist_ok=True)
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.path("vo_pickup").mkdir(parents=True, exist_ok=True)

    topo = _load_fixture("topology.json")
    adapt = _load_fixture("flow_adaptation.json")
    write_fixture_json(ctx, "understanding/source_topology.json", topo)
    write_fixture_json(ctx, "understanding/flow_adaptation.json", adapt)
    confirm_test_pickup_speaker(ctx, speaker_id=str(adapt.get("pickup_eligible_speaker_id") or "spk_1"))

    brief = minimal_content_brief(
        strategic_moat_concept="Network effects from two-sided marketplace density",
        era_tags=[{"era": "1990s", "geography": "US"}],
    )
    write_fixture_json(ctx, "understanding/content_brief.json", brief)
    write_fixture_json(ctx, "segments/manifest.json", minimal_manifest("seg_001", "seg_002"))

    state = populated_analysis_state(ctx.run_id, verified=False)
    state.setdefault("meta", {})["production_style"] = TBIY_STYLE
    state["narrative"] = {
        **(state.get("narrative") or {}),
        "thesis": "How a category leader built defensible scale.",
        "strategic_moat_concept": brief["strategic_moat_concept"],
    }
    write_fixture_json(ctx, "understanding/analysis_state.json", state)

    gap = minimal_gap_report(
        minimal_gap_line(
            line_id="line_001",
            gap_type="reaction_line",
            text="Wait — that's the moat right there.",
            voice_speaker_id="spk_1",
            delivery="record",
            post_preview=True,
        ),
        minimal_gap_line(
            line_id="line_002",
            gap_type="chapter_hook",
            text="Let's rewind to the crisis year.",
            voice_speaker_id="spk_1",
            delivery="record",
            post_preview=True,
        ),
    )

    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    meta["production_style"] = TBIY_STYLE
    write_fixture_json(ctx, "run_meta.json", meta)

    seed_flow1_sound_spend_ready(ctx)
    from interview_mux.source_topology import pickup_eligible_speaker_id

    eligible = pickup_eligible_speaker_id(ctx) or "spk_1"
    for ln in gap.get("interviewer_lines") or []:
        if isinstance(ln, dict):
            ln["voice_speaker_id"] = eligible
    write_fixture_json(ctx, "understanding/gap_report.json", gap)
    write_fixture_theme_wav(ctx, "master/assembly_preview.wav")
    mark_done_raw(ctx, "assembly_preview")

def _client_with_tbiy_run(tmp_path: Path, monkeypatch) -> tuple[TestClient, RunContext]:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_tbiy_journey", create=True)
    init_run_meta_for_test(ctx)
    seed_tbiy_journey_ctx(ctx)
    return TestClient(create_app()), ctx

def test_tbiy_topology_confirm_and_story_lock(tmp_path: Path, monkeypatch) -> None:
    client, ctx = _client_with_tbiy_run(tmp_path, monkeypatch)
    run_id = ctx.run_id

    topo_res = client.get(f"/api/runs/{run_id}/source-topology")
    assert topo_res.status_code == 200
    body = topo_res.json()
    assert body["topology"]["topology_class"] == "one_on_one_asymmetric"
    assert body["adaptation"]["pickup_eligible_speaker_id"] == "spk_1"

    confirm = client.post(f"/api/runs/{run_id}/flow-adaptation/confirm")
    assert confirm.status_code == 200
    assert confirm.json()["adaptation"]["operator_overrides"]["topology_confirmed"] is True

    state = ctx.read_json("understanding/analysis_state.json")
    state.setdefault("meta", {})["production_style"] = TBIY_STYLE
    state["narrative"]["strategic_moat_concept"] = "Regulatory capture + scale"
    put = client.put(
        f"/api/runs/{run_id}/analysis-profile",
        json={"data": state, "operator_verified": True},
    )
    assert put.status_code == 200
    assert put.json()["operator_verified"] is True

    brief = ctx.read_json("understanding/content_brief.json")
    assert brief.get("strategic_moat_concept") == "Regulatory capture + scale"
    assert is_tbiy(ctx)

def test_tbiy_g1_pickup_and_preview_g1_5_gate(tmp_path: Path, monkeypatch) -> None:
    client, ctx = _client_with_tbiy_run(tmp_path, monkeypatch)
    run_id = ctx.run_id

    pickup_dir = ctx.path("vo_pickup")
    (pickup_dir / "line_001.wav").write_bytes(MINIMAL_WAV_BYTES)
    (pickup_dir / "line_002.wav").write_bytes(MINIMAL_WAV_BYTES)

    mark_preview_listened(ctx)
    assert ctx.read_json("run_meta.json").get("preview_listened_at")

    pending = check_g1_5_preview_pickup_pending(ctx)
    assert set(pending) == {"line_001", "line_002"}

    with pytest.raises(SystemExit):
        require_g1_5_preview_pickup_clear(ctx, stage="mmaudio_sfx")

    for line_id in pending:
        from run_fixtures import write_fixture_vo_wav
        import io

        buf = io.BytesIO()
        # API upload needs speech-QA-passable bytes
        tmp = ctx.path("vo_pickup") / f"_upload_{line_id}.wav"
        write_fixture_vo_wav(tmp, duration_sec=0.6)
        wav_bytes = tmp.read_bytes()
        res = client.post(
            f"/api/runs/{run_id}/vo/{line_id}",
            files={"file": (f"{line_id}.wav", wav_bytes, "audio/wav")},
        )
        assert res.status_code == 200, res.text

    assert check_g1_5_preview_pickup_pending(ctx) == []
    require_g1_5_preview_pickup_clear(ctx, stage="mmaudio_sfx")

def test_tbiy_g1_5_stage_action_required(tmp_path: Path, monkeypatch) -> None:
    client, ctx = _client_with_tbiy_run(tmp_path, monkeypatch)
    run_id = ctx.run_id
    pickup_dir = ctx.path("vo_pickup")
    (pickup_dir / "line_001.wav").write_bytes(MINIMAL_WAV_BYTES)
    (pickup_dir / "line_002.wav").write_bytes(MINIMAL_WAV_BYTES)
    mark_preview_listened(ctx)
    res = client.get(f"/api/runs/{run_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["g1_5_preview_pickup_pending"]
    g15 = next(s for s in body["stages"] if s["id"] == "g1_5_preview_pickup")
    assert g15["status"] == "action_required"
    assert body["journey"]["blocking"]["reason"] == "gate"
    # Earlier analysis gates may still outrank G1.5 in journey blocking.
    assert body["journey"]["blocking"]["stage_id"] in {
        "g1_5_preview_pickup",
        "missing_framing",
        "framing_posture_decide",
        "g_framing",
    }

def test_tbiy_gap_report_studio_crud(tmp_path: Path, monkeypatch) -> None:
    from interview_mux import artifact_writes as aw

    real_write = aw.write_validated_artifact

    def _write(ctx, rel, data, **kwargs):
        if rel == "understanding/gap_report.json":
            kwargs["stage_key"] = "gap_framing_compose"
        return real_write(ctx, rel, data, **kwargs)

    monkeypatch.setattr(aw, "write_validated_artifact", _write)
    monkeypatch.setattr("interview_mux.gap_report_api.write_validated_artifact", _write)
    client, ctx = _client_with_tbiy_run(tmp_path, monkeypatch)
    run_id = ctx.run_id

    add = client.post(
        f"/api/runs/{run_id}/gap-report/lines",
        json={"text": "That's the insight.", "gap_type": "reaction_line"},
    )
    assert add.status_code == 200
    line_id = add.json()["line"]["line_id"]
    assert add.json()["line"]["voice_speaker_id"] in {"spk_0", "spk_1"}

    lines = client.get(f"/api/runs/{run_id}/gap-report/lines")
    assert lines.status_code == 200
    assert any(ln["line_id"] == line_id for ln in lines.json()["lines"])

    delete = client.delete(f"/api/runs/{run_id}/gap-report/lines/{line_id}")
    assert delete.status_code == 200

def test_tbiy_prompt_variants_unified(tmp_path: Path, monkeypatch) -> None:
    """TBIY dual prompts retired — always return canonical system prompt paths."""
    _, ctx = _client_with_tbiy_run(tmp_path, monkeypatch)
    from interview_mux.production_profile import prompt_variant

    assert is_tbiy(ctx)
    assert prompt_variant("selection/narrative-arc-plan.system.txt", ctx) == (
        "selection/narrative-arc-plan.system.txt"
    )
    assert prompt_variant("sound_design/plan-flow1.system.txt", ctx) == (
        "sound_design/plan-flow1.system.txt"
    )
