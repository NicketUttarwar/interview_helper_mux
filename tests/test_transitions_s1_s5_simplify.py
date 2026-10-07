"""transitions S1–S5 simplify: detect-only selection, demote synthetic, refuse incomplete glue."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from interview_mux.stages import selection
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "transitions_s1_s5")


def test_s1_no_selection_mutation_kitchen_in_run_transitions() -> None:
    src = inspect.getsource(selection.run_transitions)
    assert "drop_late_intro_reset_from_selection" not in src
    assert "drop_post_coda_reverse_jump_from_selection" not in src
    assert "commit_selection_mutation" not in src
    assert 'producer="transitions"' not in src
    assert "repair=False" in src
    assert "selection_air_order_dirty" in src or "selection air-order dirty" in src


def test_s2_contract_outputs_match_ownership() -> None:
    from pathlib import Path as P

    import yaml

    doc = yaml.safe_load(
        (P("docs/cross-cutting/stage-contracts/transitions.yaml")).read_text()
    )
    paths = {row["path"] for row in doc.get("outputs") or []}
    forbidden = {
        "master/order_reconcile.json",
        "master/rank_candidates.json",
        "master/story_health.json",
        "understanding/speaker_delivery_plan.json",
    }
    assert paths.isdisjoint(forbidden)
    assert "master/transitions.json" in paths
    assert "master/bridge_completeness.json" in paths


def test_s3a_layup_on_always_demotes_without_llm(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import synthetic_framing

    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001", "seg_002"], "excluded_segment_ids": []},
    )
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda cfg=None: True
    )
    called = {"llm": False}

    def _boom(*_a, **_k):
        called["llm"] = True
        raise AssertionError("must not call LLM under layup demote")

    monkeypatch.setattr(
        "interview_mux.llm_simple.run_llm_stage_simple", _boom
    )
    plan = synthetic_framing.run_synthetic_framing_plan(ctx)
    assert called["llm"] is False
    assert plan.get("lines") == []
    assert plan.get("demoted") is True


def test_incompleteness_honors_justified_skip_cover(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade (MUX_FORENSICS=0): justified skip / native handoff is complete glue."""
    from interview_mux.nugget_layup import PLAN_REL
    from interview_mux.stage_completion import stage_artifact_incompleteness

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "Landed hinge.",
                    "type": "chapter",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/reorder_bridges.json",
        {
            "pairs": [
                {"after_segment_id": "seg_002", "before_segment_id": "seg_003", "kind": "reorder"},
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        PLAN_REL,
        {
            "ordered_segment_ids": ["seg_001", "seg_002", "seg_003"],
            "layups": [
                {
                    "target_segment_id": "seg_003",
                    "skip": True,
                    "skip_reason_code": "listener_already_oriented",
                    "compensating_path": "The preceding native already names the next beat.",
                }
            ]
        },
        skip_handoff=True,
    )
    assert stage_artifact_incompleteness(ctx, "transitions") is None


def test_persist_mints_required_glue_before_mark_done() -> None:
    """Cascade (MUX_FORENSICS=0): persist mints hinges before Done Authority."""
    src = inspect.getsource(selection.run_transitions)
    first_mint = src.find("ensure_seam_glue")
    persist_call = src.find("persist(c, artifacts)")
    assert first_mint != -1 and persist_call != -1
    assert first_mint < persist_call


def test_s4_incomplete_glue_is_advisory(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    """ISSUES 185: incomplete glue is logged, never a SystemExit."""
    src = inspect.getsource(selection.run_transitions)
    assert "bridge_completeness incomplete after glue mint (advisory)" in src
    glue_block = src.split("ensure_seam_glue")[-1].split("stamp_transitions_pair_freeze")[0]
    assert "raise SystemExit" not in glue_block


def test_s5_bare_premature_pins_transitions_when_hollow(ctx) -> None:
    from interview_mux.stage_completion import premature_class_pin

    assert premature_class_pin("premature_complete", ctx) == "transitions"
    assert premature_class_pin("delivery:premature_complete", ctx) == "transitions"


def test_s5_bare_premature_avoids_transitions_when_complete(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stage_completion import premature_class_pin

    ctx.write_json("master/transitions.json", {"transitions": []})
    monkeypatch.setattr(
        "interview_mux.artifact_completeness.artifact_status",
        lambda rel, _ctx: "complete" if rel == "master/transitions.json" else "pending",
    )
    monkeypatch.setattr(
        "interview_mux.progression_spine.first_incomplete_flow1_spine_stage",
        lambda _ctx, **_k: "edl",
    )
    pin = premature_class_pin("premature_complete", ctx)
    assert pin == "edl"
    assert pin != "transitions"
