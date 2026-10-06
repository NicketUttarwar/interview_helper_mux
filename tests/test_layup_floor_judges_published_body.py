"""The layup floor judges hollowness on the body being published (ISSUES 159).

exec_016: the plan carried 1 live synthetic line (need 3, pool exhausted), but
the snapshot read the committed gap report, still at 0, as HOLLOW_ZERO, so
publish raised hosted_vo_floor_unsatisfiable at error level. The next call,
with the line committed, proceeded on the advisory.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from run_fixtures import isolated_run_ctx


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, aspirational: bool):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "exec_layup_floor")
    hollow = SimpleNamespace(identity=SimpleNamespace(status="HOLLOW_ZERO", cause=None), aspirational_ok=False)
    monkeypatch.setattr("interview_mux.hosted_vo_authority.floor_snapshot", lambda *a, **k: hollow)
    monkeypatch.setattr("interview_mux.floor_progress.hosted_vo_aspirational", lambda c=None: aspirational)
    proceeded: list[dict] = []
    monkeypatch.setattr(
        "interview_mux.floor_progress.proceed_on_floor_miss",
        lambda c, **k: proceeded.append(k),
    )
    errors: list[str] = []
    real_log = ctx.log

    def _log(msg, *a, **k):
        if k.get("level") == "error":
            errors.append(str(msg))
        return real_log(msg, *a, **k)

    monkeypatch.setattr(ctx, "log", _log)
    ctx._test_errors = errors
    return ctx, proceeded


def test_live_line_over_a_stale_hollow_snapshot_proceeds(tmp_path, monkeypatch) -> None:
    from interview_mux.nugget_layup import raise_hosted_vo_floor_unsatisfiable

    ctx, proceeded = _setup(tmp_path, monkeypatch, aspirational=True)
    raise_hosted_vo_floor_unsatisfiable(ctx, need=3, active=1, eligible_nuggets=1)
    assert proceeded and proceeded[0]["have"] == 1
    assert not [e for e in ctx._test_errors if "unsatisfiable" in e]


def test_hollow_publish_advisory_continues(tmp_path, monkeypatch) -> None:
    from interview_mux.nugget_layup import raise_hosted_vo_floor_unsatisfiable

    ctx, proceeded = _setup(tmp_path, monkeypatch, aspirational=True)
    raise_hosted_vo_floor_unsatisfiable(ctx, need=3, active=0, eligible_nuggets=0)
    assert proceeded and proceeded[0]["have"] == 0
    assert not [e for e in ctx._test_errors if "unsatisfiable" in e]


def test_short_floor_without_aspirational_still_advisory(tmp_path, monkeypatch) -> None:
    from interview_mux.nugget_layup import raise_hosted_vo_floor_unsatisfiable

    ctx, proceeded = _setup(tmp_path, monkeypatch, aspirational=False)
    raise_hosted_vo_floor_unsatisfiable(ctx, need=3, active=1, eligible_nuggets=1)
    assert proceeded and proceeded[0]["have"] == 1
