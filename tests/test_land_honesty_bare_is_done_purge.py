"""Bare is_done purge — hollow mark_done_raw must not skip ADVANCE/SKIP paths.

MUX_FORENSICS=0. Behavior + source guards for music-epoch skip-mark and
speaker_roles recovery skip (and remaining ADVANCE sites converted to
may_skip_as_complete / land_honest / seed_stage_complete).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.done_authority import land_honest, may_skip_as_complete
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, mark_done_raw

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src" / "interview_mux"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "bare_is_done_purge")


# ---------------------------------------------------------------------------
# Behavior: hollow stamp never counts as skip-complete
# ---------------------------------------------------------------------------


def test_hollow_mark_done_raw_not_may_skip_music_or_speaker(ctx: RunContext) -> None:
    for sid in ("mmaudio_sfx", "music_palette_compose", "speaker_roles", "edl"):
        mark_done_raw(ctx, sid)
        assert ctx.is_done(sid), sid
        assert may_skip_as_complete(ctx, sid) is False, sid
        assert land_honest(ctx, sid) is False, sid


def test_analysis_remaining_keeps_hollow_stamped_stage(ctx: RunContext) -> None:
    from interview_mux.homunculus.agenda import remaining_stages

    mark_done_raw(ctx, "speaker_roles")
    rem = remaining_stages(ctx, "analysis")
    assert "speaker_roles" in rem


def test_stalled_expensive_can_advance_false_on_hollow(ctx: RunContext) -> None:
    from interview_mux.execution_status import stalled_expensive_can_advance

    mark_done_raw(ctx, "edl")
    assert stalled_expensive_can_advance(ctx, "edl") is False


# ---------------------------------------------------------------------------
# Source guards: SKIP / ADVANCE / FORCE-DONE sites must not use bare is_done
# ---------------------------------------------------------------------------

_SKIP_ADVANCE_FILES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "pipeline.py",
        (
            "land_honest",
            "speaker_roles_dominant_fallback",
            "music epoch complete",
        ),
    ),
    (
        "homunculus/runtime.py",
        (
            "may_skip_as_complete",
            "land_honest",
            "DETECTION_ONLY_IS_DONE",
        ),
    ),
    (
        "homunculus/agenda.py",
        (
            "may_skip_as_complete",
            "land_honest",
            "DETECTION_ONLY_IS_DONE",
        ),
    ),
    (
        "execution_status.py",
        ("may_clear_wait",),
    ),
    (
        "web/runner.py",
        ("may_skip_as_complete", "may_clear_wait"),
    ),
)


def test_pipeline_music_epoch_skip_uses_land_honest_not_bare_is_done() -> None:
    text = (_SRC / "pipeline.py").read_text(encoding="utf-8")
    # Music-epoch skip block must gate on land_honest, not ctx.is_done.
    idx = text.index("music epoch complete — skip regenerate")
    window = text[max(0, idx - 600) : idx + 200]
    assert "land_honest" in window
    assert "ctx.is_done" not in window


def test_pipeline_speaker_roles_recovery_skip_uses_land_honest() -> None:
    text = (_SRC / "pipeline.py").read_text(encoding="utf-8")
    idx = text.index("speaker_roles_dominant_fallback")
    window = text[idx : idx + 500]
    assert "land_honest" in window
    assert "ctx.is_done(stage)" not in window


def test_runtime_music_epoch_skip_only_when_land_honest() -> None:
    text = (_SRC / "homunculus" / "runtime.py").read_text(encoding="utf-8")
    idx = text.index("homunculus skip-run")
    # First music-epoch skip-run site after prepare fingerprint.
    music_idx = text.index("music epoch complete", idx)
    window = text[max(0, music_idx - 800) : music_idx + 400]
    assert "land_honest" in window
    assert "if not ctx.is_done(stage)" not in window


def test_agenda_music_epoch_keep_uses_land_honest() -> None:
    text = (_SRC / "homunculus" / "agenda.py").read_text(encoding="utf-8")
    idx = text.index("homunculus keeping")
    window = text[max(0, idx - 500) : idx + 200]
    assert "land_honest" in window
    assert "if not ctx.is_done(sid)" not in window


def test_execution_status_no_bare_is_done_fallback() -> None:
    text = (_SRC / "execution_status.py").read_text(encoding="utf-8")
    idx = text.index("def stalled_expensive_can_advance")
    end = text.index("\ndef ", idx + 1)
    body = text[idx:end]
    assert "may_clear_wait" in body
    assert "ctx.is_done" not in body


def test_scoped_files_skip_advance_import_done_authority() -> None:
    for rel, needles in _SKIP_ADVANCE_FILES:
        text = (_SRC / rel).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in text, f"{rel} missing {needle}"


def test_bare_is_done_in_scoped_paths_are_detection_only_or_seed_defn() -> None:
    """Any remaining ctx.is_done in scoped ADVANCE modules must be DETECTION_ONLY
    or inside seed_stage_complete / producer_ready definitions.
    """
    # Files where ADVANCE/SKIP must not use bare is_done without DETECTION_ONLY.
    critical = (
        "pipeline.py",
        "homunculus/runtime.py",
        "execution_status.py",
        "web/runner.py",
    )
    for rel in critical:
        text = (_SRC / rel).read_text(encoding="utf-8")
        for m in re.finditer(r"ctx\.is_done\(", text):
            start = max(0, m.start() - 200)
            window = text[start : m.start()]
            assert (
                "DETECTION_ONLY_IS_DONE" in window
                or "seed_stage_complete" in text[: m.start()][-80:]
            ), f"{rel}:{text[:m.start()].count(chr(10))+1} bare is_done without DETECTION_ONLY"


def test_delivery_guardrails_music_epoch_reseats_without_bare_or() -> None:
    text = (_SRC / "delivery_guardrails.py").read_text(encoding="utf-8")
    idx = text.index("def music_epoch_complete")
    end = text.index("\ndef ", idx + 1)
    body = text[idx:end]
    assert "seed_stage_complete(ctx, sid) or ctx.is_done" not in body
    assert "if seed_stage_complete(ctx, sid):" in body
