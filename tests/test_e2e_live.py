"""Live full E2E — skipped unless E2E_LIVE=1."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("E2E_LIVE") != "1",
    reason="Set E2E_LIVE=1 to run live full-application E2E",
)


def test_live_placeholder():
    assert True
