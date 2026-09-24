"""Forensics must not leapfrog nugget_layup_compose past incomplete seed-front.

exec_13174: driver cleared hosted_vo_floor / layup needs_operator and re_executed
layup every ~3s while narrative_arc_plan was still incomplete → heal-spin.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import apply_premature_cap_for_execute
from run_fixtures import isolated_run_ctx


def test_forensics_layup_premature_cap_pins_narrative_not_layup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "layup_defer_seed")
    # Incomplete narrative seed-front: no narrative_plan, no layup plan.
    assert not ctx.artifact_exists("master/narrative_plan.json")

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.premature_cap_hard_pin",
        lambda _ctx, resume, message="": "narrative_arc_plan",
    )
    cap = apply_premature_cap_for_execute(
        ctx,
        "nugget_layup_compose",
        automation=True,
        message="hosted_vo_floor_unmet",
    )
    assert cap["ok"] is True
    assert cap["rewritten"] is True
    assert cap["from_stage"] == "narrative_arc_plan"
    assert cap["from_stage"] != "nugget_layup_compose"


def test_forensics_layup_defer_helper_in_driver_source() -> None:
    """Source contract: layup resume goes through seed-front defer helper."""
    src = Path(__file__).resolve().parents[1] / "tools" / "full_auto_driver.py"
    text = src.read_text(encoding="utf-8")
    assert "def _forensics_layup_resume_or_wait(" in text
    assert "defer layup" in text
    # Both forensics layup execute sites must call the helper, not raw layup.
    idx = text.find("def _forensics_layup_resume_or_wait(")
    assert idx > 0
    # After helper definition, hosted_vo_floor resume must use it.
    after = text[idx:]
    assert "_forensics_layup_resume_or_wait(" in after
    assert 'resume via seed-front defer' in after
    # Must not keep the old unconditional layup execute in the idle path.
    idle_marker = "cleared needs_operator hosted_vo_floor"
    idle_idx = after.find(idle_marker)
    assert idle_idx > 0
    window = after[idle_idx : idle_idx + 500]
    assert "resume via seed-front defer" in window
    assert '"from_stage": "nugget_layup_compose"' not in window
