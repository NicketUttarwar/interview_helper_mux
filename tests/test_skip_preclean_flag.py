"""MUX_SKIP_PRECLEAN=1 dismisses audio_preclean instead of accepting DeepFilter."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from interview_mux.stages.audio_preclean import preclean_was_skipped
from run_fixtures import isolated_run_ctx, patch_executions_root

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import full_auto_daemon_launch as dal  # noqa: E402
import full_auto_driver as driver  # noqa: E402


@pytest.fixture(autouse=True)
def _forensics_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")


class _FakePrecleanCtx:
    def __init__(
        self,
        *,
        done: bool = False,
        ingest_done: bool = False,
        decisions: list[dict[str, Any]] | None = None,
    ) -> None:
        self._done = done
        self._ingest_done = ingest_done
        self._decisions = decisions

    def is_done(self, stage: str) -> bool:
        if stage == "audio_preclean":
            return self._done
        if stage == "ingest":
            return self._ingest_done
        return False

    def artifact_exists(self, rel: str) -> bool:
        return rel == "run_meta.json"

    def read_json(self, _rel: str) -> dict[str, Any]:
        if self._decisions:
            return {"audio_preclean": {"decisions": self._decisions}}
        return {}


def _stub_open_preclean(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    monkeypatch.setattr(driver, "RUN_ID", "exec_skip_preclean")
    monkeypatch.setattr(driver, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(driver, "log_decision", lambda *_a, **_k: None)
    monkeypatch.setattr(driver, "is_partial_auto", lambda: False)
    monkeypatch.setattr(driver, "deepfilter_runtime_ok", lambda: True)
    monkeypatch.setattr(
        "interview_mux.run_context.RunContext",
        lambda *_a, **_k: _FakePrecleanCtx(),
    )
    monkeypatch.setattr(
        "interview_mux.stages.audio_preclean.preclean_was_skipped",
        lambda _ctx: False,
    )
    called: list[tuple[Any, ...]] = []

    def fake_api(method: str, path: str, body: Any = None, timeout: int = 60) -> dict[str, Any]:
        called.append((method, path, body))
        return {}

    monkeypatch.setattr(driver, "api", fake_api)
    return called


def test_skip_preclean_requested_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_SKIP_PRECLEAN", "1")
    assert driver.skip_preclean_requested() is True
    monkeypatch.setenv("MUX_SKIP_PRECLEAN", "0")
    assert driver.skip_preclean_requested() is False
    monkeypatch.delenv("MUX_SKIP_PRECLEAN", raising=False)
    assert driver.skip_preclean_requested() is False


def test_skip_preclean_flag_posts_dismiss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_SKIP_PRECLEAN", "1")
    called = _stub_open_preclean(monkeypatch)

    driver.dismiss_preclean()

    assert len(called) == 1
    method, path, body = called[0]
    assert method == "POST"
    assert path.endswith("/preclean-offer")
    assert body == {
        "checkpoint": "before_ingest",
        "action": "dismiss",
        "scope": "full_source",
    }


def test_skip_preclean_unset_still_accepts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUX_SKIP_PRECLEAN", raising=False)
    called = _stub_open_preclean(monkeypatch)

    driver.dismiss_preclean()

    assert len(called) == 1
    assert called[0][2]["action"] == "accept"


def test_skip_preclean_does_not_probe_deepfilter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_SKIP_PRECLEAN", "1")
    called = _stub_open_preclean(monkeypatch)
    probed: list[bool] = []

    def boom() -> bool:
        probed.append(True)
        raise AssertionError("DeepFilter probe must not run when skip is set")

    monkeypatch.setattr(driver, "deepfilter_runtime_ok", boom)
    driver.accept_preclean()
    assert called[0][2]["action"] == "dismiss"
    assert probed == []


def test_driver_env_forwards_skip_preclean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_SKIP_PRECLEAN", "1")
    env = dal._driver_env(
        port=8765,
        audio="ASSETS/input/interview.wav",
        keep_gui_server=True,
        partial_auto=False,
    )
    assert env["MUX_SKIP_PRECLEAN"] == "1"
    monkeypatch.delenv("MUX_SKIP_PRECLEAN", raising=False)
    env_off = dal._driver_env(
        port=8765,
        audio="ASSETS/input/interview.wav",
        keep_gui_server=True,
        partial_auto=False,
    )
    assert "MUX_SKIP_PRECLEAN" not in env_off


def test_api_dismiss_writes_skip_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "exec_skip_preclean_api")
    from interview_mux.stages.audio_preclean import ensure_preclean_skipped

    ensure_preclean_skipped(
        ctx,
        checkpoint="before_ingest",
        scope="full_source",
        reason="mux_skip_preclean",
    )
    assert ctx.artifact_exists("preclean/skip.json")
    assert preclean_was_skipped(ctx) is True
    skip = ctx.read_json("preclean/skip.json")
    assert skip["reason"] == "mux_skip_preclean"
    assert skip["status"] == "skipped"


def test_skip_preclean_marks_done_and_unblocks_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dismiss must stamp audio_preclean done so seed-order does not pin ingest."""
    from interview_mux.delivery_guardrails import seed_stage_complete
    from interview_mux.homunculus.agenda import stage_outputs_present
    from interview_mux.homunculus.runtime import _seed_prereq_block
    from interview_mux.stages.audio_preclean import ensure_preclean_skipped

    monkeypatch.setenv("MUX_FORENSICS", "0")
    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "exec_skip_preclean_seed")
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "homunculus_kind": "homunculus",
            "run_mode": "full-auto",
            "full_auto": True,
        },
        skip_handoff=True,
    )
    ensure_preclean_skipped(
        ctx,
        checkpoint="before_ingest",
        scope="full_source",
        reason="mux_skip_preclean",
    )
    assert ctx.artifact_exists("preclean/skip.json")
    assert stage_outputs_present(ctx, "audio_preclean") is True
    assert ctx.is_done("audio_preclean")
    assert seed_stage_complete(ctx, "audio_preclean") is True
    assert _seed_prereq_block(ctx, "ingest") is None
