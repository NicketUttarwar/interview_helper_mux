"""Tests for vo_line_adjudicate stage (Phase 3) and 5C delivery reorder."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.stages import vo_line_adjudicate as vo_line_adjudicate_stage
from interview_mux.v2.config import ALL_LLM_STAGES, DELIVERY_ORDER
from interview_mux.vo_line_adjudicate import (
    apply_adjudicate_results,
    line_adjudication_input_hash,
    lines_needing_adjudication,
    run_adjudicate_batches,
    run_intro_compose,
    score_layup_flow_fit,
)
from interview_mux.vo_synthesis_audit import nuke_all_synth_wavs_on_adjudicate_change
from run_fixtures import isolated_run_ctx, write_fixture_vo_wav


def _gap_with_body_line(**line_patch) -> dict:
    line = {
        "line_id": "vo_layup_seg_002",
        "gap_type": "nugget_layup",
        "text": "Before we hear how the buyer reacted, one detail sets up the pivot.",
        "targets_segment_id": "seg_002",
        "placement": "before",
        "delivery": "synthesize",
        "nugget_ids": ["nug_001"],
        "forward_unlock": "Why the snack pivot decided the price",
    }
    line.update(line_patch)
    return {"interviewer_lines": [line]}


def _corpus() -> dict:
    return {
        "nuggets": [
            {
                "nugget_id": "nug_001",
                "text_claim": "Snack insight",
                "evidence_quote": "as a snack",
                "salience": "high",
                "in_selection": False,
            },
            {
                "nugget_id": "nug_002",
                "text_claim": "Buyer pivot",
                "evidence_quote": "the buyer paused",
                "salience": "high",
                "in_selection": False,
            },
        ]
    }


def test_score_layup_flow_fit_rewards_bridge_not_restate():
    masks = {
        "natives": {
            "seg_002": {
                "comprehensible_text": "The buyer walked away from the deal after seeing the margin sheet.",
            }
        }
    }
    line = {
        "text": "One margin detail explains why the buyer hesitated before this clip.",
        "targets_segment_id": "seg_002",
        "forward_unlock": "Why the snack pivot decided the price",
    }
    target = masks["natives"]["seg_002"]["comprehensible_text"]
    score = score_layup_flow_fit(line, target, masks)
    assert score > 0.2


def test_lines_needing_adjudication_skips_unchanged_hash(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "adj_hash")
    gap = _gap_with_body_line()
    plan = {
        "layups": [
            {
                "line_id": "vo_layup_seg_002",
                "target_segment_id": "seg_002",
                "forward_unlock": "Why the snack pivot decided the price",
            }
        ]
    }
    line = gap["interviewer_lines"][0]
    input_hash = line_adjudication_input_hash(line, plan["layups"][0])
    ctx.write_json(
        "understanding/vo_line_adjudication.json",
        {
            "lines": [
                {
                    "line_id": "vo_layup_seg_002",
                    "action": "air",
                    "input_hash": input_hash,
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json("understanding/native_comprehension_masks.json", {"natives": {}}, skip_handoff=True)
    need = lines_needing_adjudication(ctx, gap, plan, threshold=0.99)
    assert need == []


def test_apply_adjudicate_rewrite_nukes_wavs(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "adj_rewrite")
    ctx.write_json("run_meta.json", {"homunculus_version": "0.1.0"}, skip_handoff=True)
    gap = _gap_with_body_line()
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    wav = ctx.path("vo_pickup/vo_layup_seg_002.wav")
    write_fixture_vo_wav(wav)
    ctx.mark_done("vo_synthesize")
    ctx.mark_done("edl_narrative_audit")

    updated, actions = apply_adjudicate_results(
        ctx,
        gap,
        [
            {
                "line_id": "vo_layup_seg_002",
                "action": "rewrite",
                "final_text": "Rewritten bridge into the buyer reaction.",
            }
        ],
    )
    assert actions[0]["action"] == "rewrite"
    assert "Rewritten bridge" in updated["interviewer_lines"][0]["text"]
    assert not wav.is_file()
    assert not ctx.is_done("vo_synthesize")
    assert not ctx.is_done("edl_narrative_audit")


def test_run_adjudicate_batches_mockable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "adj_batch")
    gap = _gap_with_body_line()
    captured: dict = {}

    def fake_runner(_ctx, _stage, _prompt, build_input, persist):
        payload = build_input(_ctx)
        artifacts = {
            "lines": [
                {
                    "line_id": payload["lines"][0]["line_id"],
                    "action": "air",
                    "input_hash": payload["lines"][0]["input_hash"],
                }
            ]
        }
        persist(_ctx, artifacts)
        return {"status": "complete", "artifacts": artifacts}

    rows = run_adjudicate_batches(
        ctx,
        ["vo_layup_seg_002"],
        gap,
        llm_runner=fake_runner,
    )
    assert rows and rows[0]["action"] == "air"
    assert ctx.artifact_exists("understanding/vo_line_adjudication.json")


def test_intro_compose_mints_position_zero(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "adj_intro")
    ctx.write_json("run_meta.json", {"homunculus_version": "0.1.0"}, skip_handoff=True)
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001", "seg_002"]}, skip_handoff=True)
    ctx.write_json("understanding/nugget_corpus.json", _corpus(), skip_handoff=True)
    gap = _gap_with_body_line()
    gap["_adjudicate_deferred_nuggets"] = ["nug_002"]

    def fake_intro(_ctx, _stage, _prompt, _build, persist):
        persist(
            _ctx,
            {
                "text": "Two forces collided before the first clip: snack economics and buyer nerve.",
                "nugget_ids": ["nug_002"],
                "intro_nugget_recovery": True,
            },
        )
        return {"status": "complete"}

    updated, intro_ids = run_intro_compose(ctx, gap, llm_runner=fake_intro)
    assert intro_ids
    lines = updated["interviewer_lines"]
    assert lines[0]["line_category"] == "episode_preface"
    assert lines[0].get("intro_nugget_recovery") is True
    assert ctx.artifact_exists("understanding/nugget_intro_compose.json")


def test_stage_skips_for_original_brain(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "adj_skip")
    ctx.write_json("run_meta.json", {"homunculus_version": "0.0.0"}, skip_handoff=True)
    vo_line_adjudicate_stage.run_vo_line_adjudicate(ctx)
    # Skip path refuses hollow marks when adjudication artifacts are absent.
    assert not ctx.is_done("vo_line_adjudicate")


def test_nuke_all_synth_wavs_on_adjudicate_change(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "adj_nuke")
    ctx.write_json(
        "understanding/gap_report.json",
        _gap_with_body_line(),
        skip_handoff=True,
    )
    write_fixture_vo_wav(ctx.path("vo_pickup/vo_layup_seg_002.wav"))
    ctx.mark_done("vo_synthesize")
    removed = nuke_all_synth_wavs_on_adjudicate_change(ctx)
    assert removed >= 1
    assert not ctx.is_done("vo_synthesize")
