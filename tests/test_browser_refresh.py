"""Browser hard-refresh helpers for scripts/run.sh launches."""

from __future__ import annotations

import pytest

from interview_mux.browser_refresh import (
    cache_busted_url,
    force_browser_hard_refresh,
    should_force_browser_refresh,
)


def test_should_force_browser_refresh_when_run_sh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_LAUNCHED_VIA", "run.sh")
    monkeypatch.delenv("MUX_NO_BROWSER_REFRESH", raising=False)
    assert should_force_browser_refresh() is True


def test_should_force_browser_refresh_opt_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_LAUNCHED_VIA", "run.sh")
    monkeypatch.setenv("MUX_NO_BROWSER_REFRESH", "1")
    assert should_force_browser_refresh() is False


def test_should_force_browser_refresh_other_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUX_LAUNCHED_VIA", raising=False)
    assert should_force_browser_refresh() is False


def test_cache_busted_url() -> None:
    assert cache_busted_url("http://127.0.0.1:8765", now=1.0) == "http://127.0.0.1:8765/?_mux_launch=1"
    assert cache_busted_url("http://127.0.0.1:8765/", now=2.0) == "http://127.0.0.1:8765/?_mux_launch=2"


def test_force_browser_hard_refresh_non_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("interview_mux.browser_refresh.sys.platform", "linux")
    assert force_browser_hard_refresh("http://127.0.0.1:8765") is False
