"""Shared pytest fixtures — outbound network guard for offline simulated tests."""

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
                "Use simulated_services.apply_simulated_services() or monkeypatch."
            )
    return _ORIGINAL_CONNECT(self, address)


@pytest.fixture(autouse=True)
def block_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block external HTTP/TCP; allow localhost for FastAPI TestClient."""
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
