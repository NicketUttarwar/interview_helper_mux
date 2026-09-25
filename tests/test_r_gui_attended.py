"""Residual GUI attended smoke — G0/G1 ALLOW, EDL DENY (no browser).

Extends ownership role fixtures: gap_report GUI ALLOW + edl GUI DENY already
live in test_gui_ownership_role.py; this module adds catalog G0/G1 paths.
"""

from __future__ import annotations

import pytest

from interview_mux.artifact_ownership import (
    AuthorityDenied,
    assert_write,
    write_permitted,
)
from run_fixtures import isolated_run_ctx

# G0 / G1 gate paths from artifact_ownership explicit GUI ALLOW catalog.
_G0_G1_GUI_PATHS = (
    "transcript/review_queue.json",  # G0
    "transcript/full.json",  # G0 companion
    "understanding/gap_report.json",  # G1 / framing
    "understanding/gap_fill_skip.json",  # G1 skip
)


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_ARTIFACT_OWNERSHIP_FAIL_CLOSED", "1")
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "r_gui_attended")


def test_r_gui_gap_report_allow(ctx) -> None:
    from test_gui_ownership_role import test_gui_gap_report_allow as _t

    _t(ctx)


def test_r_gui_edl_denied(ctx) -> None:
    from test_gui_ownership_role import test_gui_edl_denied as _t

    _t(ctx)


def test_r_gui_g0_g1_catalog_write_permitted(ctx) -> None:
    mutations = {
        "transcript/review_queue.json": "g0_edit",
        "transcript/full.json": "g0_edit",
        "understanding/gap_report.json": "g_framing",
        "understanding/gap_fill_skip.json": "g1_consent",
    }
    for path in _G0_G1_GUI_PATHS:
        ok, reason = write_permitted(
            ctx,
            path,
            None,
            role="gui",
            verb="persist",
            mutation_class=mutations[path],
        )
        assert ok, f"{path}: {reason}"
        assert reason != "anonymous_legacy"
        deny_ok, deny_reason = write_permitted(
            ctx, path, None, role="gui", verb="persist"
        )
        if deny_ok:
            assert deny_reason in {"operational", "allow", "ops"}
        else:
            assert "pin_only" in deny_reason or "not_allow" in deny_reason


def test_r_gui_edl_write_permitted_denied(ctx) -> None:
    ok, reason = write_permitted(
        ctx, "master/edl.json", "artifact_editor", role="gui", verb="persist"
    )
    assert not ok
    with pytest.raises(AuthorityDenied):
        assert_write(ctx, "master/edl.json", "artifact_editor", role="gui")
