"""0E: soft_pass_pre_edl_delivery refuses stubs without LAST_RESORT soft."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from run_fixtures import isolated_run_ctx

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import full_auto_driver as driver  # noqa: E402

_STUB_RELS = (
    "understanding/nugget_corpus.json",
    "master/transitions.json",
    "master/edl_narrative_audit.json",
)
_MARK_STAGES = (
    "nugget_corpus_mine",
    "information_package_plan",
    "nugget_layup_compose",
    "refinement_agenda",
    "gap_framing_recompose",
    "selection_framing_apply",
    "transitions",
    "sound_design_plan",
    "sound_design_vo_finalize",
    "edl_narrative_audit",
)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.delenv("INTERVIEW_MUX_E2E_LAST_RESORT_SOFT", raising=False)
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    run = isolated_run_ctx(tmp_path, "soft_pass_refuse")
    run.path("master").mkdir(parents=True, exist_ok=True)
    run.path("understanding").mkdir(parents=True, exist_ok=True)
    return run


def test_soft_pass_pre_edl_refuses_without_last_resort(ctx, monkeypatch) -> None:
    """MUX_FORENSICS=0 + no LAST_RESORT → [] and no stub artifacts / stage_done."""
    import json

    notes = driver.soft_pass_pre_edl_delivery(ctx)
    assert notes == []
    brief = Path(ctx.run_dir) / "e2e_failure_brief.json"
    assert brief.is_file(), "refuse must write e2e_failure_brief.json"
    doc = json.loads(brief.read_text(encoding="utf-8"))
    assert doc.get("suggested_fix_class") == "e2e_stub"
    for rel in _STUB_RELS:
        assert not ctx.artifact_exists(rel), f"stub created: {rel}"
    for sid in _MARK_STAGES:
        assert not ctx.is_done(sid), f"stage marked done: {sid}"


def test_soft_pass_pre_edl_refuses_when_e2e_soft_off(ctx, monkeypatch) -> None:
    monkeypatch.delenv("INTERVIEW_MUX_E2E_SOFT", raising=False)
    monkeypatch.setenv("INTERVIEW_MUX_E2E_LAST_RESORT_SOFT", "1")
    notes = driver.soft_pass_pre_edl_delivery(ctx)
    assert notes == []
    for rel in _STUB_RELS:
        assert not ctx.artifact_exists(rel)


def test_soft_pass_last_resort_stubs_when_explicit(ctx, monkeypatch) -> None:
    """Isolated LAST_RESORT=1 + e2e_soft → stubs + heal marks allowed."""
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    monkeypatch.setenv("INTERVIEW_MUX_E2E_LAST_RESORT_SOFT", "1")
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(
        ctx.path("understanding/nugget_layup_plan.json"),
        {"layups": [], "_meta": {"producer_stage": "nugget_layup_compose"}},
    )

    def _mark(c, sid):
        done = c.path(".stage_done")
        done.mkdir(parents=True, exist_ok=True)
        (done / sid).write_text("1", encoding="utf-8")

    with patch.object(driver, "_heal_mark", _mark):
        notes = driver.soft_pass_pre_edl_delivery(ctx)
    assert notes, "last-resort soft must stub/mark"
    assert ctx.artifact_exists("master/transitions.json")
    assert ctx.artifact_exists("master/edl_narrative_audit.json")


def test_heal_markers_hard_stop_on_soft_pass_refuse(ctx, monkeypatch) -> None:
    """Call site contract: empty soft_pass must not continue heal-marks."""
    monkeypatch.delenv("INTERVIEW_MUX_E2E_LAST_RESORT_SOFT", raising=False)
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    notes = driver.soft_pass_pre_edl_delivery(ctx)
    assert notes == []
    # Simulate call-site halt: refuse means no subsequent _heal_mark of soft stages.
    for sid in _MARK_STAGES:
        assert not ctx.is_done(sid)
