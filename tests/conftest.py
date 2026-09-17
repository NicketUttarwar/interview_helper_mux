"""Shared pytest fixtures — outbound network guard for offline unit tests."""

from __future__ import annotations

import os
import socket

import pytest

_ALLOWED_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_ORIGINAL_CONNECT = socket.socket.connect


def _guarded_connect(self, address) -> None:  # type: ignore[no-untyped-def]
    if isinstance(address, tuple) and len(address) >= 1:
        host = address[0]
        if isinstance(host, str) and not host.startswith("/") and host not in _ALLOWED_HOSTS:
            raise RuntimeError(
                f"Outbound network blocked in tests (connect to {host!r}). "
                "Use monkeypatch to stub external calls."
            )
    return _ORIGINAL_CONNECT(self, address)


@pytest.fixture(autouse=True)
def block_outbound_network(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Block external HTTP/TCP; allow localhost for FastAPI TestClient.

    Opt out with ``@pytest.mark.allow_network`` or ``@pytest.mark.slow`` (live MusicGen).
    """
    if request.node.get_closest_marker("allow_network") or request.node.get_closest_marker("slow"):
        return
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)


@pytest.fixture(autouse=True)
def fast_gpu_abort_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must not pay the real 30s abort backoff between mocked runtimes."""
    monkeypatch.setenv("INTERVIEW_MUX_GPU_ABORT_BACKOFF_SEC", "0")


@pytest.fixture(autouse=True)
def fast_gpu_exclusive_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must not pay the real 5s local_gpu settle between mocked runtimes."""
    monkeypatch.setenv("INTERVIEW_MUX_GPU_COOLDOWN_SEC", "0")


@pytest.fixture(autouse=True)
def clear_write_staging_context() -> None:
    """ContextVar staging must not leak across tests (writes route into .pending_writes)."""
    from interview_mux.write_staging import exit_stage_staging

    exit_stage_staging()
    yield
    exit_stage_staging()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="run @pytest.mark.slow live-model tests (MusicGen weights, minutes each)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: live / long-running integration (MusicGen weights)")
    config.addinivalue_line("markers", "allow_network: permit outbound sockets")


def _slow_enabled(config: pytest.Config) -> bool:
    return bool(config.getoption("--run-slow")) or str(
        os.environ.get("MUX_RUN_SLOW_TESTS") or ""
    ).strip().lower() in {"1", "true", "yes", "on"}


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """`slow` is opt-in: `--run-slow` or `MUX_RUN_SLOW_TESTS=1`.

    These tests load real MusicGen weights and generate audio. When the weights
    happen to be cached they do not skip and do not time out — they just run, for
    tens of minutes each, which makes a plain `pytest tests/` unusable. The
    existing `_musicgen_ready()` guards only skip when the weights are *missing*,
    so the better-provisioned the machine, the worse the suite behaves.

    Gating the marker rather than the individual tests keeps the capability
    tests intact and reachable on demand.
    """
    if _slow_enabled(config):
        return
    skip_slow = pytest.mark.skip(
        reason="live-model test: pass --run-slow or set MUX_RUN_SLOW_TESTS=1"
    )
    for item in items:
        if item.get_closest_marker("slow"):
            item.add_marker(skip_slow)
