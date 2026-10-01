"""Partial DONE is the package stage's product for the current master (ISSUES 111).

A completed run re-entered at an earlier stage keeps its publish files on
disk. They must not count as DONE: the package stage's marker is gone, and
once the master is rebuilt the package is older than it.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from interview_mux.execution_status import (
    package_bound_to_current_master,
    pipeline_complete,
    ship_bar_incomplete_reasons,
)
from run_fixtures import isolated_run_ctx


def _complete_run(tmp_path: Path):
    ctx = isolated_run_ctx(tmp_path, "pkg_bound")
    master = ctx.final_path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"\0" * 4096)
    pub = ctx.final_path("publish")
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "cover.jpg").write_bytes(b"jpg")
    (pub / "audio.mp3").write_bytes(b"mp3")
    ctx.write_json("publish/package_ready.json", {"ready": True})
    done = ctx.final_path(".stage_done")
    done.mkdir(parents=True, exist_ok=True)
    (done / "podcast_publish").write_text("")
    return ctx


def _older(path: Path, than: Path, seconds: float = 120.0) -> None:
    t = than.stat().st_mtime - seconds
    os.utime(path, (t, t))


def test_a_complete_run_is_done(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.execution_status.committed_master_present", lambda c: True)
    ctx = _complete_run(tmp_path)
    assert package_bound_to_current_master(ctx) is True
    assert pipeline_complete(ctx) is True


def test_a_rewound_run_is_not_done_while_its_old_package_remains(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.execution_status.committed_master_present", lambda c: True)
    ctx = _complete_run(tmp_path)
    ctx.final_path(".stage_done", "podcast_publish").unlink()
    assert pipeline_complete(ctx) is False
    assert "podcast_publish_not_done" in ship_bar_incomplete_reasons(ctx)


def test_a_rebuilt_master_makes_the_old_package_stale(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.execution_status.committed_master_present", lambda c: True)
    ctx = _complete_run(tmp_path)
    pkg = ctx.final_path("publish", "package_ready.json")
    master = ctx.final_path("master", "master.wav")
    _older(pkg, master)
    assert package_bound_to_current_master(ctx) is False
    assert pipeline_complete(ctx) is False
    assert "package_older_than_master" in ship_bar_incomplete_reasons(ctx)
    # The package stage running again binds it to the new master.
    time.sleep(0.01)
    ctx.write_json("publish/package_ready.json", {"ready": True})
    now = time.time()
    os.utime(pkg, (now + 1, now + 1))
    assert pipeline_complete(ctx) is True
