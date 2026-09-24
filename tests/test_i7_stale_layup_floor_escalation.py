"""i7: stale hosted_vo_floor escalation must not block Chatterbox after seats remint."""

from __future__ import annotations

import json
import os

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.delivery_guardrails import _layup_escalation_blocking
from interview_mux.gap_fill_eligibility import count_active_gap_vo_lines
from run_fixtures import init_run_meta_for_test, isolated_run_ctx


def _write(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_i7_stale_floor_escalation_clears_when_seats_present(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_i7_esc")
    init_run_meta_for_test(ctx)
    _write(
        ctx,
        "operator/escalations/nugget_layup_compose.json",
        {
            "status": "open",
            "reason": "hosted_vo_floor_unsatisfiable",
            "need": 3,
            "active": 0,
        },
    )
    _write(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "text": "Welcome to today's conversation with our guest.",
                    "delivery": "synthesize",
                    "targets_segment_id": "seg_001",
                }
            ]
        },
    )
    assert count_active_gap_vo_lines(ctx) >= 1
    assert not _layup_escalation_blocking(ctx)
    esc = ctx.read_json("operator/escalations/nugget_layup_compose.json")
    assert str(esc.get("status") or "").lower() == "cleared"
