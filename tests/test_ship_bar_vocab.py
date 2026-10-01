"""SHIP_BAR_VOCAB (DP-C5) — pipeline_complete is sole Partial DONE.

MUX_FORENSICS=0. G-Publish / S3 consent is never this bar.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.delivery_invariants import MIN_COMMITTED_MASTER_BYTES
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "ship_bar_vocab")


def _commit_master(run_ctx) -> None:
    master_dir = run_ctx.final_path("master")
    master_dir.mkdir(parents=True, exist_ok=True)
    (master_dir / "master.wav").write_bytes(
        b"RIFF" + b"\x00" * MIN_COMMITTED_MASTER_BYTES
    )
    (master_dir / "post_master_quality.json").write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-09-21T00:00:00Z",
                "status": "pass",
                "publish_allowed": True,
                "failed_checks": [],
                "checks": {},
                "never_skipped": True,
            }
        ),
        encoding="utf-8",
    )
    done = run_ctx.final_path(".stage_done", "master_finalize")
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("")


def _local_package(run_ctx, *, ready: bool = True, skipped: bool = False) -> None:
    pub = run_ctx.final_path("publish")
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "cover.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 32)
    (pub / "audio.mp3").write_bytes(b"ID3" + b"\x00" * 64)
    run_ctx.write_json(
        "publish/package_ready.json",
        {"ready": ready, "skipped": skipped, "version": 1},
        skip_handoff=True,
    )
    if ready:
        # A real package comes with its stage's marker, written after it
        # (ISSUES 111: the bar binds the package to the stage and the master).
        done = run_ctx.final_path(".stage_done")
        done.mkdir(parents=True, exist_ok=True)
        (done / "podcast_publish").write_text("")


def test_pipeline_complete_requires_package_envelope(ctx) -> None:
    from interview_mux.execution_status import (
        pipeline_complete,
        ship_bar_complete,
        ship_bar_incomplete_reasons,
    )

    assert pipeline_complete(ctx) is False
    assert "master_missing_or_thin" in ship_bar_incomplete_reasons(ctx)

    _commit_master(ctx)
    assert pipeline_complete(ctx) is False
    reasons = ship_bar_incomplete_reasons(ctx)
    assert "cover_missing" in reasons
    assert "audio_mp3_missing" in reasons

    pub = ctx.final_path("publish")
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "cover.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 32)
    (pub / "audio.mp3").write_bytes(b"ID3" + b"\x00" * 64)
    assert pipeline_complete(ctx) is False
    assert "package_ready_missing_or_false" in ship_bar_incomplete_reasons(ctx)

    # Hollow stage markers must not flip DONE without package_ready.
    done = ctx.final_path(".stage_done")
    (done / "podcast_publish").write_text("")
    (done / "episode_cover_generate").write_text("")
    assert pipeline_complete(ctx) is False

    _local_package(ctx, ready=True)
    assert pipeline_complete(ctx) is True
    assert ship_bar_complete(ctx) is True
    assert ship_bar_incomplete_reasons(ctx) == []


def test_package_ready_skipped_is_not_local_done(ctx) -> None:
    """C5 footgun #2: Skip seed-completes publish stage but not Partial DONE."""
    from interview_mux.execution_status import pipeline_complete

    _commit_master(ctx)
    _local_package(ctx, ready=False, skipped=True)
    assert pipeline_complete(ctx) is False


def test_g_publish_meta_does_not_affect_ship_bar(ctx) -> None:
    """C5: S3 / g_publish_cleared must not be required for pipeline_complete."""
    from interview_mux.execution_status import (
        g_publish_consent_is_not_ship_bar,
        pipeline_complete,
    )

    _commit_master(ctx)
    _local_package(ctx, ready=True)
    ctx.mutate_run_meta(
        lambda m: m.update(
            {
                "g_publish_cleared": False,
                "g_publish_pending": True,
                "s3_sync_ok": False,
            }
        )
    )
    assert g_publish_consent_is_not_ship_bar() is True
    assert pipeline_complete(ctx) is True


def test_esr_short_circuits_when_ship_bar_complete(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.execution_status import should_wait_incomplete_after_conductor

    monkeypatch.setattr(
        "interview_mux.thrash_hardening.expensive_stage_lease_active",
        lambda _c: (False, ""),
    )
    _commit_master(ctx)
    _local_package(ctx, ready=True)
    assert should_wait_incomplete_after_conductor(ctx, pin="mix") is None
    assert should_wait_incomplete_after_conductor(ctx, pin="podcast_publish") is None


def test_ship_remaining_empty_when_package_ready(ctx) -> None:
    from interview_mux.execution_status import pipeline_complete
    from interview_mux.homunculus.agenda import ship_after_master_remaining

    _commit_master(ctx)
    _local_package(ctx, ready=True)
    # Cover + package_ready satisfy protected outputs for ship stages that key them.
    left = ship_after_master_remaining(ctx)
    assert pipeline_complete(ctx) is True
    # Remaining may still list transcript if missing — that is work list, not DONE lie.
    assert "podcast_publish" not in left


def test_vocabulary_table_documents_five_predicates() -> None:
    from interview_mux.execution_status import SHIP_BAR_VOCABULARY

    assert "pipeline_complete" in SHIP_BAR_VOCABULARY
    assert "g_publish / S3" in SHIP_BAR_VOCABULARY
    assert "Partial DONE" in SHIP_BAR_VOCABULARY["pipeline_complete"]
    assert "never part of ship bar" in SHIP_BAR_VOCABULARY["g_publish / S3"].lower()


def test_driver_fallback_matches_package_envelope() -> None:
    from pathlib import Path

    src = Path("tools/full_auto_driver.py").read_text(encoding="utf-8")
    assert "package_ready.json" in src
    assert "G-Publish / S3 consent is not this bar" in src
    # Must not treat bare .stage_done/podcast_publish as DONE in the fallback.
    fallback = src[src.find("def pipeline_complete()") : src.find("def assert_fresh_layer_contract()")]
    assert "package_ready" in fallback
    assert 'done_dir / "podcast_publish"' not in fallback
