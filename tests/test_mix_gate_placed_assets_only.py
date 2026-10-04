"""The mix gate refuses only QA failures the mix will place (ISSUES 151)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux import mix_completeness as mc
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "exec_mix_gate")
    dest = c.final_path("sound_design", "placement_adjustments.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps({"version": 1, "adjustments": [{"asset_id": "ast_stinger_03", "action": "skip_cue"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.referenced_musicgen_asset_ids",
        lambda _c: {"ast_bed_open", "ast_stinger_03"},
    )
    return c


def test_skipped_and_unreferenced_failures_do_not_block(ctx) -> None:
    assert mc.qa_failures_that_block_mix(ctx, {"ast_stinger_03", "ast_orphan_take"}) == set()


def test_a_placed_failure_still_blocks(ctx) -> None:
    assert mc.qa_failures_that_block_mix(ctx, {"ast_bed_open"}) == {"ast_bed_open"}
