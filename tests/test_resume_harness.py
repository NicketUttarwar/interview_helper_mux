"""The resume harness's judgements: what counts as complete, stale, an error, a gate to sign."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from run_fixtures import isolated_run_ctx, mark_done_raw

_spec = importlib.util.spec_from_file_location(
    "resume_harness", Path(__file__).resolve().parents[1] / "tools" / "resume_harness.py"
)
harness = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
# Dataclasses resolve their module through sys.modules while the class body runs.
sys.modules["resume_harness"] = harness
_spec.loader.exec_module(harness)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_complete_needs_the_publish_marker_and_a_package_newer_than_the_master(tmp_path) -> None:
    import os

    run = tmp_path / "run"
    assert harness._complete(run) is False
    _write(run / ".stage_done" / "podcast_publish", "")
    assert harness._complete(run) is False
    _write(run / "master" / "master.wav", "w")
    _write(run / "publish" / "package_ready.json", "{}")
    assert harness._complete(run) is True
    # A master rebuilt after the package means the package stage did not run again (ISSUES 111).
    t = (run / "publish" / "package_ready.json").stat().st_mtime + 60
    os.utime(run / "master" / "master.wav", (t, t))
    assert harness._complete(run) is False


def test_error_lines_are_the_error_level_log_rows_only(tmp_path) -> None:
    run = tmp_path / "run"
    rows = [
        {"level": "info", "stage": "mix", "message": "fine"},
        {"level": "error", "stage": "edl", "message": "EDL QC failed"},
        {"level": "warning", "stage": "mix", "message": "meh"},
        {"level": "error", "stage": "mix", "message": "boom"},
    ]
    _write(run / "gui_log.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
    assert harness._error_lines(run) == ["[edl] EDL QC failed", "[mix] boom"]


def test_stale_staging_counts_only_finished_stages(tmp_path) -> None:
    run = tmp_path / "run"
    _write(run / ".pending_writes" / "mix" / "master" / "assembly_ledger.json", "{}")
    _write(run / ".pending_writes" / "edl" / "master" / "edl.json", "{}")
    _write(run / ".pending_writes" / "edl" / ".write.lock", "")
    _write(run / ".stage_done" / "edl", "")
    assert harness._stale_staging(run) == ["edl/master/edl.json"]


def test_sign_off_acts_once_per_gate_through_the_real_functions(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_harness_gates")
    calls: list[str] = []
    monkeypatch.setattr("interview_mux.gates.check_transcript_review_pending", lambda c: True)
    monkeypatch.setattr(
        "interview_mux.stages.transcript_review.mark_transcript_review_complete",
        lambda c: calls.append("g0"),
    )
    monkeypatch.setattr(
        "interview_mux.gates.clear_g_publish", lambda c, skipped=False: calls.append(f"publish:{skipped}")
    )
    signed: list[str] = []
    harness._sign_off(ctx, {"status": "gate", "stage": "transcript_review"}, signed, final="skip")
    harness._sign_off(ctx, {"status": "gate", "stage": "transcript_review"}, signed, final="skip")
    harness._sign_off(ctx, {"status": "running", "stage": "mix"}, signed, final="skip")
    harness._sign_off(ctx, {"status": "gate", "stage": "g_publish"}, signed, final="skip")
    assert calls == ["g0", "publish:True"]
    assert signed == ["transcript_review", "g_publish"]


def test_rewind_drops_the_final_sign_off_and_publish_marker(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_harness_rewind")
    mark_done_raw(ctx, "podcast_publish")
    ctx.mutate_run_meta(lambda m: m.update({"g_publish_cleared": True, "g_publish_pending": False}))
    cleared: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(ctx, "clear_from", lambda stage, order: cleared.append((stage, list(order))))
    harness._rewind(ctx, "mix")
    assert cleared and cleared[0][0] == "mix" and "podcast_publish" in cleared[0][1]
    assert not ctx.is_done("podcast_publish")
    meta = ctx.read_json("run_meta.json")
    assert "g_publish_cleared" not in meta


def test_presets_name_real_stages() -> None:
    from interview_mux.pipeline import effective_delivery_order
    from interview_mux.v2.config import ANALYSIS_ORDER

    known = set(ANALYSIS_ORDER) | set(effective_delivery_order())
    for stages in (harness.BOUNDARY_STAGES, harness.CRASH_STAGES):
        assert set(stages) <= known
