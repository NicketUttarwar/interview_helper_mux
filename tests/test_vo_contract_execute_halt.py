"""VO contract execute failures must halt — never infinite log_transient_retry."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_driver():
    root = Path(__file__).resolve().parents[1]
    path = root / "tools" / "full_auto_driver.py"
    spec = importlib.util.spec_from_file_location("full_auto_driver_halt", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_permanent_vs_transient_execute_classification() -> None:
    d = _load_driver()
    permanent = RuntimeError(
        "POST /api/runs/x/execute -> 500: {'detail': "
        "'VO contract: seated synthesize vo_preface_precision_oncology has skip/omit flags'}"
    )
    transient = RuntimeError(
        "GET /api/runs/x/job: <urlopen error [Errno 61] Connection refused>"
    )
    assert d._is_permanent_execute_error(permanent)
    assert not d._is_transient_execute_error(permanent)
    assert d._is_transient_execute_error(transient)
    assert not d._is_permanent_execute_error(transient)


def test_identical_permanent_execute_bumps_to_halt_threshold() -> None:
    d = _load_driver()
    d._IDENTICAL_STAGE_FAILURES.clear()
    exc = RuntimeError(
        "POST /api/runs/x/execute -> 500: {'detail': "
        "'VO contract: seated synthesize vo_preface_x has skip/omit flags'}"
    )
    keys = []
    counts = []
    for _ in range(3):
        key, count = d._bump_permanent_execute_failure(exc)
        keys.append(key)
        counts.append(count)
    assert keys[0] == keys[1] == keys[2]
    assert counts == [1, 2, 3]
    assert "vo contract" in keys[0]
