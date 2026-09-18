"""Stage Clinic Wave 2 — podcast_publish (B1/B2/B3/B4/B5/B6).

No real S3/CloudFront/AWS CLI — host honesty + mocked sync only.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.homunculus.agenda import stage_outputs_present
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import stage_artifact_incompleteness
from interview_mux.stages.podcast_publish import run_podcast_publish_skip
from run_fixtures import patch_executions_root

_EID = "exec_900_abcdefabcdef_20260101T120000Z"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext(_EID, create=True)
    run.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "homunculus_kind": "homunculus",
            "execution_id": run.run_id,
            "g_publish_pending": True,
        },
        skip_handoff=True,
    )
    return run


def test_ppub_b1_skip_package_ready_ready_false_skipped(ctx: RunContext) -> None:
    """Clinic B1: Skip writes package_ready ready:false skipped — seed-complete."""
    run_podcast_publish_skip(ctx)
    doc = ctx.read_json("publish/package_ready.json")
    assert isinstance(doc, dict)
    assert doc.get("ready") is False
    assert doc.get("skipped") is True
    result = ctx.read_json("publish/publish_result.json")
    assert result.get("skipped") is True
    assert ctx.is_done("podcast_publish")
    assert stage_outputs_present(ctx, "podcast_publish") is True
    assert stage_artifact_incompleteness(ctx, "podcast_publish") is None
    assert seed_stage_complete(ctx, "podcast_publish") is True


def test_ppub_b1_ready_false_without_skipped_still_hollow(ctx: RunContext) -> None:
    """Bare ready:false (no skipped) remains HPUB-2 hollow."""
    ctx.write_json(
        "publish/package_ready.json",
        {"ready": False},
        skip_handoff=True,
    )
    assert stage_outputs_present(ctx, "podcast_publish") is False
    reason = stage_artifact_incompleteness(ctx, "podcast_publish")
    assert reason is not None
    assert "ready is not true" in reason


def test_ppub_b3_b5_contract_hard_mp3_cover_vtt_soft_trimmed() -> None:
    """Clinic B3/B5: hard=wav+mp3+cover+VTT; over-soft inputs removed."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("podcast_publish")
    assert c is not None
    hard = {d.path: d.producer for d in c.inputs if d.hard and d.path}
    soft = {d.path for d in c.inputs if not d.hard and d.path}
    assert hard.get("master/master.wav") == "master_finalize"
    assert hard.get("publish/audio.mp3") == "podcast_encode_mp3"
    assert hard.get("publish/cover.jpg") == "episode_cover_generate"
    assert hard.get("master/transcript.vtt") == "master_transcript_build"
    assert "master/transcript.json" not in soft
    assert "segments/manifest.json" not in soft
    assert "understanding/gap_report.json" not in soft
    assert "understanding/speakers.json" not in soft
    assert "publish/audio.mp3" not in soft
    assert "master/transcript.vtt" not in soft
    assert "master/edl.json" in soft
    assert "publish/episode_meta.json" in soft


def test_ppub_b4_require_g_publish_clear_is_dead() -> None:
    """Clinic B4: KEEP DEAD — require_g_publish_clear defined, never called."""
    root = Path(__file__).resolve().parents[1] / "src" / "interview_mux"
    callers: list[str] = []
    for path in root.rglob("*.py"):
        if path.name == "gates.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name == "require_g_publish_clear":
                    callers.append(str(path.relative_to(root)))
    assert callers == []


def test_ppub_b2_b6_full_auto_advisory_refuse_remote_no_hang(
    ctx: RunContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PPUB-B2: DONE-local / refuse-remote — no auto-consent; Full-auto clears hang."""
    from interview_mux.gates import check_g_publish_pending
    from interview_mux.podcast_rss import sync_assets

    exec_root = patch_executions_root(monkeypatch, tmp_path)
    ctx.write_json(
        "run_meta.json",
        {
            "execution_id": ctx.run_id,
            "full_auto": True,
            "homunculus_version": "0.2.0",
            "quality_advisories": [
                {"gate_id": "listenability_contract", "failed_checks": ["x"]}
            ],
            "g_publish_pending": True,
        },
        skip_handoff=True,
    )
    publish = ctx.final_path("publish")
    publish.mkdir(parents=True, exist_ok=True)
    for name in ("audio.mp3", "master.wav", "cover.jpg", "chapters.json", "transcript.vtt"):
        (publish / name).write_bytes(b"x" * 64)
    (publish / "package_ready.json").write_text(
        json.dumps({"ready": True, "title": "Adv"}),
        encoding="utf-8",
    )
    ctx.write_json(
        "publish/publish_result.json",
        {"local_package": True, "uploaded": False, "execution_id": ctx.run_id},
        skip_handoff=True,
    )
    ctx.mark_done("podcast_publish")

    with (
        patch.object(
            sync_assets,
            "require_publish_ready",
            return_value={
                "bucket": "b",
                "region": "us-east-1",
                "distribution_id": "E123",
                "feed_base_url": "https://d.example",
                "project_name": "the_war_room_001",
            },
        ),
        patch.object(sync_assets, "get_json", return_value={}),
        patch.object(sync_assets, "write_last_sync_result"),
        patch.object(sync_assets, "upload_episode_files") as upload,
    ):
        result = sync_assets.sync_ready_packages(
            dry_run=False,
            execution_id=ctx.run_id,
            exec_root=exec_root,
        )

    assert upload.call_count == 0
    reasons = [e.get("reason") for e in (result.errors or []) if isinstance(e, dict)]
    assert "publish_blocked_quality_advisories" in reasons
    meta = ctx.read_json("run_meta.json")
    assert meta.get("g_publish_remote_refused") is True
    assert meta.get("g_publish_advisory_consent") is not True
    assert meta.get("g_publish_pending") is False
    assert check_g_publish_pending(ctx) is False
    pr = ctx.read_json("publish/publish_result.json")
    assert pr.get("remote_refused") is True
    assert pr.get("uploaded") is False


def test_ppub_b2_partial_keeps_pending_on_advisory_refuse(
    ctx: RunContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Partial: advisory refuse stamps remote_refused but keeps pending (must-act)."""
    from interview_mux.gates import check_g_publish_pending
    from interview_mux.podcast_rss import sync_assets

    exec_root = patch_executions_root(monkeypatch, tmp_path)
    ctx.write_json(
        "run_meta.json",
        {
            "execution_id": ctx.run_id,
            "partial_auto": True,
            "homunculus_version": "0.2.0",
            "quality_advisories": [
                {"gate_id": "listenability_contract", "failed_checks": ["x"]}
            ],
            "g_publish_pending": True,
        },
        skip_handoff=True,
    )
    publish = ctx.final_path("publish")
    publish.mkdir(parents=True, exist_ok=True)
    for name in ("audio.mp3", "master.wav", "cover.jpg", "chapters.json", "transcript.vtt"):
        (publish / name).write_bytes(b"x" * 64)
    (publish / "package_ready.json").write_text(
        json.dumps({"ready": True, "title": "Partial"}),
        encoding="utf-8",
    )
    ctx.write_json(
        "publish/publish_result.json",
        {"local_package": True, "uploaded": False},
        skip_handoff=True,
    )
    ctx.mark_done("podcast_publish")

    with (
        patch.object(
            sync_assets,
            "require_publish_ready",
            return_value={
                "bucket": "b",
                "region": "us-east-1",
                "distribution_id": "E123",
                "feed_base_url": "https://d.example",
                "project_name": "the_war_room_001",
            },
        ),
        patch.object(sync_assets, "get_json", return_value={}),
        patch.object(sync_assets, "write_last_sync_result"),
        patch.object(sync_assets, "upload_episode_files"),
    ):
        sync_assets.sync_ready_packages(
            dry_run=False,
            execution_id=ctx.run_id,
            exec_root=exec_root,
        )

    meta = ctx.read_json("run_meta.json")
    assert meta.get("g_publish_remote_refused") is True
    assert meta.get("g_publish_pending") is True
    assert check_g_publish_pending(ctx) is True
