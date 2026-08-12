"""Shared pytest fixtures — outbound network guard for offline unit tests."""

from __future__ import annotations

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
def fast_gpu_exclusive_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must not pay the real 5s local_gpu settle between mocked runtimes."""
    monkeypatch.setenv("INTERVIEW_MUX_GPU_COOLDOWN_SEC", "0")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: live / long-running integration (MusicGen weights)")
    config.addinivalue_line("markers", "allow_network: permit outbound sockets")
