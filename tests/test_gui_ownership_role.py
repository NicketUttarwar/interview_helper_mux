"""0D GUI role ALLOW / DENY fixtures under fail-closed ownership."""

from __future__ import annotations

import pytest

from interview_mux.artifact_ownership import (
    AuthorityDenied,
    assert_write,
    write_permitted,
)
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_ARTIFACT_OWNERSHIP_FAIL_CLOSED", "1")
    return isolated_run_ctx(tmp_path, "gui_role")


def test_gui_gap_report_allow(ctx) -> None:
    ok, reason = write_permitted(
        ctx, "understanding/gap_report.json", None, role="gui", verb="persist"
    )
    assert ok, reason
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        role="gui",
        skip_handoff=True,
    )


def test_gui_edl_denied(ctx) -> None:
    ok, reason = write_permitted(
        ctx, "master/edl.json", "artifact_editor", role="gui", verb="persist"
    )
    assert not ok
    assert "gui" in reason or "deny" in reason or "not_allow" in reason or "edl" in reason
    with pytest.raises(AuthorityDenied):
        assert_write(ctx, "master/edl.json", "artifact_editor", role="gui")


def test_gui_skip_optional_not_anonymous_legacy(ctx) -> None:
    ok, reason = write_permitted(
        ctx, "understanding/gap_report.json", None, role="gui", verb="persist"
    )
    assert ok
    assert reason != "anonymous_legacy"
