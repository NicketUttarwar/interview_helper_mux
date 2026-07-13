"""BUILD-072 — pre-clean quality offer API and run_meta persistence."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interview_mux.session_log import read_log
from interview_mux.gates import check_g1_vo
from interview_mux.web.server import (
    _build_stage_list,
    _default_scope_for_checkpoint,
    _record_preclean_offer,
    create_app,
)
from run_fixtures import init_run_meta_for_test, isolated_run_ctx, minimal_gap_report, patch_server_ctx

def _seed_g1_complete(ctx) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(),
    )
    pickup = ctx.path("vo_pickup")
    pickup.mkdir(parents=True, exist_ok=True)
    (pickup / "line_001.wav").write_bytes(b"RIFF")
    script = ctx.path("understanding/interviewer_script.txt")
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("Can you add context here?\n", encoding="utf-8")

def test_default_scope_for_checkpoint() -> None:
    assert _default_scope_for_checkpoint("g1_vo_pickup") == "vo_pickup"
    assert _default_scope_for_checkpoint("before_ingest") == "full_source"

def test_preclean_offer_logs_offer_accept_dismiss(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_900")
    init_run_meta_for_test(ctx)

    changed, _ = _record_preclean_offer(
        ctx, checkpoint="before_ingest", action="offer", scope=None
    )
    assert changed
    messages = [e["message"] for e in read_log(ctx.run_dir)]
    assert any("Quality offer shown" in m for m in messages)

    changed, payload = _record_preclean_offer(
        ctx, checkpoint="g1_vo_pickup", action="accept", scope="vo_pickup"
    )
    assert changed
    assert payload["enabled"] is True
    assert payload["scope"] == "vo_pickup"
    meta = ctx.read_json("run_meta.json")
    assert meta["audio_preclean"]["scope"] == "vo_pickup"
    assert "g1_vo_pickup" in meta["audio_preclean"]["offered_at"]
    decisions = meta["audio_preclean"]["decisions"]
    assert decisions[-1]["action"] == "accept"
    assert decisions[-1]["scope"] == "vo_pickup"
    messages = [e["message"] for e in read_log(ctx.run_dir)]
    assert "g1_pickup_preclean_accepted" in messages

    _record_preclean_offer(ctx, checkpoint="before_ingest", action="dismiss", scope=None)
    meta = ctx.read_json("run_meta.json")
    assert meta["audio_preclean"]["enabled"] is False
    assert ctx.is_done("audio_preclean")
    assert ctx.artifact_exists("preclean/skip.json")
    messages = [e["message"] for e in read_log(ctx.run_dir)]
    assert any("dismissed" in m and "before_ingest" in m for m in messages)

def test_preclean_offer_accept_invalidates_markers(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_901")
    init_run_meta_for_test(ctx)
    ctx.mark_done("ingest")
    ctx.mark_done("transcribe")
    patch_server_ctx(monkeypatch, ctx)

    client = TestClient(create_app())
    res = client.post(
        f"/api/runs/{ctx.run_id}/preclean-offer",
        json={"checkpoint": "before_ingest", "action": "accept", "scope": "full_source"},
    )
    assert res.status_code == 200
    assert res.json()["audio_preclean"]["enabled"] is True
    assert not ctx.is_done("ingest")

def test_preclean_offer_api_rejects_unknown_checkpoint(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_902")
    init_run_meta_for_test(ctx)
    patch_server_ctx(monkeypatch, ctx)

    client = TestClient(create_app())
    for checkpoint in ("not_a_checkpoint", "after_g0", "before_flow_mix"):
        res = client.post(
            f"/api/runs/{ctx.run_id}/preclean-offer",
            json={"checkpoint": checkpoint, "action": "offer"},
        )
        assert res.status_code == 400

def test_preclean_offer_idempotent_offer(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_903")
    init_run_meta_for_test(ctx)

    _record_preclean_offer(ctx, checkpoint="before_ingest", action="offer", scope=None)
    log_path = ctx.run_dir / "gui_log.jsonl"
    count_after_first = sum(1 for _ in log_path.open())

    changed, _ = _record_preclean_offer(
        ctx, checkpoint="before_ingest", action="offer", scope=None
    )
    assert changed is False
    count_after_second = sum(1 for _ in log_path.open())
    assert count_after_second == count_after_first

def test_g1_complete_preclean_offer_logs_offered(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_904")
    init_run_meta_for_test(ctx)
    _seed_g1_complete(ctx)

    changed, _ = _record_preclean_offer(
        ctx, checkpoint="g1_vo_pickup", action="offer", scope=None
    )
    assert changed
    messages = [e["message"] for e in read_log(ctx.run_dir)]
    assert "g1_pickup_preclean_offered" in messages

def test_g1_complete_stage_status_done(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_905")
    init_run_meta_for_test(ctx)
    _seed_g1_complete(ctx)

    stages = _build_stage_list(ctx, check_g1_vo(ctx), False, True, False)
    g1 = next(s for s in stages if s["id"] == "g1_vo_pickup")
    assert g1["status"] == "done"

def test_dismiss_unblocks_ingest_guidance(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_907")
    init_run_meta_for_test(ctx)

    _record_preclean_offer(ctx, checkpoint="before_ingest", action="dismiss", scope=None)

    from interview_mux.stage_guidance import build_stage_guidance

    guidance = build_stage_guidance(ctx, "ingest", status="pending")
    prereq_todos = [p for p in guidance["prerequisites"] if p.get("status") == "todo"]
    assert not any(p.get("stage_id") == "audio_preclean" for p in prereq_todos)

    stages = _build_stage_list(ctx, check_g1_vo(ctx), False, True, False)
    preclean = next(s for s in stages if s["id"] == "audio_preclean")
    ingest = next(s for s in stages if s["id"] == "ingest")
    assert preclean["status"] in ("done", "incomplete")
    assert ctx.artifact_exists("preclean/skip.json")
    assert ingest["status"] == "pending"

def test_g1_pickup_preclean_accept_invalidates_vo_ingest(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_906")
    init_run_meta_for_test(ctx)
    _seed_g1_complete(ctx)
    ctx.mark_done("vo_ingest")
    ctx.mark_done("edl")
    patch_server_ctx(monkeypatch, ctx)

    client = TestClient(create_app())
    res = client.post(
        f"/api/runs/{ctx.run_id}/preclean-offer",
        json={"checkpoint": "g1_vo_pickup", "action": "accept", "scope": "vo_pickup"},
    )
    assert res.status_code == 200
    assert res.json()["audio_preclean"]["enabled"] is True
    assert res.json()["audio_preclean"]["scope"] == "vo_pickup"
    assert not ctx.is_done("vo_ingest")
    assert not ctx.is_done("edl")
    messages = [e["message"] for e in read_log(ctx.run_dir)]
    assert "g1_pickup_preclean_accepted" in messages
