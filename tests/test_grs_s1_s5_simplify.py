"""gap_report_sanitize S1–S5 simplify pins (high-risk audit MODE=fix)."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from interview_mux.artifact_ownership import AuthorityDenied, gap_report_body_text_changed
from interview_mux.artifact_sanitize.gap_report import (
    _resolve_gap_land_producer,
    _strip_scaffolding,
    commit_gap_report_doc,
    gap_layup_coverage_errors,
    run_gap_report_sanitize,
    sanitize_gap_report,
)
from interview_mux.done_authority import unpaid_land_reason
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "grs_s1_s5")


def _write_selection(ctx: RunContext, ids: list[str]) -> None:
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ids,
            "excluded_segment_ids": [],
            "chapters": [],
            "order_content_hash": "sel_hash_test",
        },
        skip_handoff=True,
    )


def _dump_gap(ctx: RunContext, doc: dict) -> None:
    path = ctx.path("understanding/gap_report.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_s1_preserve_layup_producer_stage(ctx: RunContext) -> None:
    _write_selection(ctx, ["seg_001"])
    _dump_gap(
        ctx,
        {
            "version": 1,
            "interviewer_lines": [
                {
                    "line_id": "vo_a",
                    "text": "Clean layup line.",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                    "gap_type": "missing_question",
                }
            ],
            "gaps": [],
            "_meta": {"producer_stage": "nugget_layup_compose"},
        },
    )
    run_gap_report_sanitize(ctx)
    disk = ctx.read_json("understanding/gap_report.json")
    assert (disk.get("_meta") or {}).get("producer_stage") == "nugget_layup_compose"
    assert unpaid_land_reason(ctx, "gap_report_sanitize") is None


def test_s1_resolve_helper_claims_when_unpaid() -> None:
    assert (
        _resolve_gap_land_producer(prior="", claim="gap_report_sanitize")
        == "gap_report_sanitize"
    )
    assert (
        _resolve_gap_land_producer(
            prior="nugget_layup_compose", claim="gap_report_sanitize"
        )
        == "nugget_layup_compose"
    )
    assert (
        _resolve_gap_land_producer(
            prior="nugget_layup_compose", claim="nugget_layup_compose"
        )
        == "nugget_layup_compose"
    )


def test_s2_no_rewrite_speaker_role_in_strip() -> None:
    src = inspect.getsource(_strip_scaffolding)
    assert "rewrite_speaker_role_labels" not in src
    row = {
        "line_id": "vo_req",
        "required": True,
        "text": "Welcome back — in today's episode we unpack the trial.",
    }
    fixed, changed = _strip_scaffolding(row)
    assert changed is False
    assert fixed.get("text") == row["text"]


def test_s3_coverage_not_in_sanitize_errors(ctx: RunContext) -> None:
    from interview_mux.stage_completion import PRODUCER_PIN_TABLE

    _write_selection(ctx, [f"seg_{i:03d}" for i in range(1, 11)])
    thin = {
        "nugget_layup_authority": True,
        "_meta": {"compose_thin": True, "producer_stage": "nugget_layup_compose"},
        "interviewer_lines": [
            {
                "line_id": "vo_only",
                "text": "one line",
                "targets_segment_id": "seg_001",
                "placement": "before",
                "delivery": "synthesize",
                "gap_type": "missing_question",
            }
        ],
        "gaps": [],
    }
    result = sanitize_gap_report(ctx, thin)
    assert result.ok
    assert not any("layup_coverage" in e for e in result.errors)
    assert gap_layup_coverage_errors(ctx, thin)
    assert PRODUCER_PIN_TABLE.get("layup_coverage_below_floor") == "nugget_layup_compose"
    import interview_mux.stage_completion as sc

    assert "gap_layup_coverage_errors" in inspect.getsource(sc)

def test_s4_framing_yes_missing_no_stub(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled",
        lambda _c: True,
    )
    with pytest.raises(RuntimeError, match="missing while framing"):
        run_gap_report_sanitize(ctx)
    assert not ctx.artifact_exists("understanding/gap_report.json")


def test_s5_stamp_commit_refuses_body_text_mutate(ctx: RunContext) -> None:
    prior = {
        "version": 1,
        "interviewer_lines": [
            {
                "line_id": "vo_a",
                "text": "Original spoken copy.",
                "targets_segment_id": "seg_001",
                "placement": "before",
                "delivery": "synthesize",
                "gap_type": "missing_question",
            }
        ],
        "gaps": [],
        "_meta": {"producer_stage": "nugget_layup_compose"},
    }
    _dump_gap(ctx, prior)
    mutated = {
        **prior,
        "interviewer_lines": [
            {
                **prior["interviewer_lines"][0],
                "text": "Foreign stamp rewrite — must refuse.",
            }
        ],
    }
    assert gap_report_body_text_changed(prior, mutated) is True
    with pytest.raises(AuthorityDenied):
        commit_gap_report_doc(
            ctx,
            mutated,
            reason="stamp_test",
            stage_key="gap_report_sanitize",
        )
