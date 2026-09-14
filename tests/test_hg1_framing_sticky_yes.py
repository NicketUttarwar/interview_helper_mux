"""HG-1: driver stamps G-Framing Yes only when the gate is pending.

Clone-voice heal may force Yes. Pre-check exceptions still continue.
Do not start a run. HC-5 overlay stays later.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, patch_executions_root

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import full_auto_driver as driver  # noqa: E402


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_hg1_framing", create=True)
    init_run_meta_for_test(run)
    monkeypatch.setattr(driver, "RUN_ID", run.run_id)
    monkeypatch.setattr(driver, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(driver, "log_decision", lambda *_a, **_k: None)
    monkeypatch.setattr(driver, "_pipeline_native_only", lambda: False)
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.silent_skip_allowed",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.assess_gap_fill_eligibility",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.clear_gap_fill_skip",
        lambda *_a, **_k: None,
    )
    return run


def _fake_api(*, pending: bool) -> tuple[list[tuple[str, str]], Any]:
    calls: list[tuple[str, str]] = []

    def api(method: str, path: str, body: dict | None = None, timeout: int = 180) -> dict:
        calls.append((method, path))
        if "gap-framing" in path and method == "GET":
            return {"gap_framing_decision_pending": pending}
        if "pickup-speaker" in path:
            return {"pending": False, "pickup_speaker_confirmed": True}
        return {}

    return calls, api


def test_hg1_not_pending_does_not_stamp_yes(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, api = _fake_api(pending=False)
    monkeypatch.setattr(driver, "api", api)
    driver.accept_gap_framing_defaults()
    meta = ctx.read_json("run_meta.json")
    assert meta.get("gap_framing_enabled") is not True
    assert not any(c[0] == "POST" and "gap-framing/enable" in c[1] for c in calls)


def test_hg1_pending_posts_and_stamps_yes(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, api = _fake_api(pending=True)
    monkeypatch.setattr(driver, "api", api)
    driver.accept_gap_framing_defaults()
    meta = ctx.read_json("run_meta.json")
    assert meta.get("gap_framing_enabled") is True
    assert meta.get("gap_fill_mode") == "active"
    assert any(c[0] == "POST" and "gap-framing/enable" in c[1] for c in calls)


def test_hg1_precheck_exception_still_posts_when_pending(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom() -> bool:
        raise RuntimeError("precheck")

    monkeypatch.setattr(driver, "_pipeline_native_only", boom)
    calls, api = _fake_api(pending=True)
    monkeypatch.setattr(driver, "api", api)
    driver.accept_gap_framing_defaults()
    meta = ctx.read_json("run_meta.json")
    assert meta.get("gap_framing_enabled") is True
    assert any(c[0] == "POST" and "gap-framing/enable" in c[1] for c in calls)


def test_hg1_clone_voice_force_yes_when_not_pending(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, api = _fake_api(pending=False)
    monkeypatch.setattr(driver, "api", api)
    driver.accept_gap_framing_defaults(force_yes=True)
    meta = ctx.read_json("run_meta.json")
    assert meta.get("gap_framing_enabled") is not True
    assert not any(c[0] == "POST" and "gap-framing/enable" in c[1] for c in calls)


def test_hg1_operator_no_not_overwritten(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.mutate_run_meta(lambda m: m.update({"gap_framing_enabled": False}))
    calls, api = _fake_api(pending=True)
    monkeypatch.setattr(driver, "api", api)
    driver.accept_gap_framing_defaults()
    meta = ctx.read_json("run_meta.json")
    assert meta.get("gap_framing_enabled") is False
    driver.accept_gap_framing_defaults(force_yes=True)
    meta = ctx.read_json("run_meta.json")
    assert meta.get("gap_framing_enabled") is False
