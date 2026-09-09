"""5583-class: selection_unsanitary incompleteness pins selection_order_sanitize."""

from __future__ import annotations

from pathlib import Path

from interview_mux.run_context import RunContext
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx, patch_executions_root


def test_selection_unsanitary_heal_navigate_pins_sanitize(
    tmp_path: Path, monkeypatch
) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "exec_5583_pin")
    (ctx.run_dir / ".stage_done" / "nugget_layup_compose").write_text(
        "done\n", encoding="utf-8"
    )
    reason = (
        "selection_unsanitary — resume selection_order_sanitize: "
        "fragment_depth_exceeded"
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, stage: reason if stage == "nugget_layup_compose" else None,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.registry.selection_sanitary_errors",
        lambda _ctx: ["fragment_depth_exceeded"],
    )
    nav = heal_navigate(
        ctx,
        error=reason,
        stage="nugget_layup_compose",
    )
    assert nav["from_stage"] == "selection_order_sanitize"
    assert nav["from_stage"] != "nugget_layup_compose"


def test_parse_resume_stage_from_reason_allowlisted() -> None:
    from interview_mux.stage_completion import parse_resume_stage_from_reason

    assert (
        parse_resume_stage_from_reason(
            "selection_unsanitary — resume selection_order_sanitize: depth"
        )
        == "selection_order_sanitize"
    )
    assert parse_resume_stage_from_reason("no resume token here") is None
