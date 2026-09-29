"""The MusicGen parent drains the child's pipes while polling (ISSUES 84)."""

from __future__ import annotations

import contextlib
import sys
import time
from pathlib import Path

import pytest

from interview_mux import musicgen_runner as mg

CHATTY = """\
import sys
# More than any pipe buffer holds: a per-tensor progress bar looks like this.
for i in range(12000):
    sys.stderr.write("Loading checkpoint shards: %d/12000 [00:00<00:00, 999it/s]\\n" % i)
sys.stderr.flush()
print("ok")
"""


@pytest.fixture
def no_gpu_gate(monkeypatch):
    @contextlib.contextmanager
    def _gate(*a, **k):
        yield

    monkeypatch.setattr("interview_mux.gpu_exclusive.gpu_exclusive", _gate)
    monkeypatch.setattr(mg, "cli_python_executable", lambda p: Path(sys.executable))


def test_child_that_floods_stderr_finishes_instead_of_deadlocking(tmp_path, no_gpu_gate) -> None:
    script = tmp_path / "chatty.py"
    script.write_text(CHATTY, encoding="utf-8")
    req = tmp_path / "req.json"
    req.write_text("{}", encoding="utf-8")
    t0 = time.monotonic()
    result = mg._spawn_musicgen(
        py=Path(sys.executable), script=script, req=req, timeout=60, role="theme", run_ctx=None
    )
    elapsed = time.monotonic() - t0
    assert result.returncode == 0, result.stderr[-300:]
    assert result.stdout.strip() == "ok"
    assert "12000" in result.stderr.split("\n")[-2]  # every line drained, not truncated
    assert elapsed < 30, f"took {elapsed:.1f}s: the parent waited on an undrained pipe"


def test_timeout_still_kills_and_keeps_the_stderr_tail(tmp_path, no_gpu_gate) -> None:
    script = tmp_path / "hang.py"
    script.write_text(
        "import sys, time\nsys.stderr.write('loading...\\n'); sys.stderr.flush(); time.sleep(120)\n",
        encoding="utf-8",
    )
    req = tmp_path / "req.json"
    req.write_text("{}", encoding="utf-8")
    monkeypatch_wait = 1
    result = mg._spawn_musicgen(
        py=Path(sys.executable), script=script, req=req, timeout=monkeypatch_wait, role=None, run_ctx=None
    )
    assert result.returncode == -9
    assert "timeout after" in result.stderr
    assert "loading..." in result.stderr


def test_child_env_disables_progress_bars(tmp_path) -> None:
    req = tmp_path / "req.json"
    req.write_text('{"model_id": "facebook/musicgen-small"}', encoding="utf-8")
    env = mg.hub_env_for_request(req, tmp_path / "hf_cache")
    assert env["TQDM_DISABLE"] == "1"
    assert env["HF_HUB_DISABLE_PROGRESS_BARS"] == "1"
