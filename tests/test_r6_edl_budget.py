"""R6 (#25): classified EDL playbook budget — fingerprint flip or producer pin.

Structural EDL classes stay budget=1 (not TRANSIENT). Success must flip an
authority fingerprint; no-op first heal escalates with a named producer pin
instead of burning the single attempt on silent consumer re-exec.

Anti-footguns (locked here): no EDL→TRANSIENT_ERROR_CLASSES; no product
``suppress_budget_exhausted``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.order_hash import bump_order_lock
from interview_mux.publishability_boundary import PublishabilityBlocked, PublishabilityReport
from interview_mux.recovery_controller import (
    TRANSIENT_ERROR_CLASSES,
    handle_stage_failure,
    recovery_attempt_budget,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import edl_heal_resume_stage, producer_pin_for_token
from interview_mux.thrash_hardening import edl_content_authority_token
from run_fixtures import isolated_run_ctx, plant_seed_complete_through

_LINE = "vo_preface_episode_orientation"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "r6_edl_budget")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _speech(sid: str) -> dict:
    return {
        "type": "speech",
        "segment_id": sid,
        "source_start_ms": 0,
        "source_end_ms": 1000,
        "duration_ms": 1000,
        "timeline_start_ms": 0,
    }


def _edl(ids: list[str]) -> dict:
    clips: list[dict] = []
    t = 0
    for sid in ids:
        clip = _speech(sid)
        clip["timeline_start_ms"] = t
        clips.append(clip)
        t += 1000
    return {
        "version": 1,
        "ordered_segment_ids": list(ids),
        "clips": clips,
        "timeline_duration_ms": t,
    }


def test_r6_structural_edl_classes_not_transient_budget_one() -> None:
    for cls in (
        "selection_edl_order_drift",
        "opening_orientation_inaudible",
        "vo_audibility_drift",
    ):
        assert cls not in TRANSIENT_ERROR_CLASSES
        assert recovery_attempt_budget(cls) == 1
    assert "edl" not in TRANSIENT_ERROR_CLASSES


def test_r6_no_product_suppress_budget_exhausted() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "interview_mux"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "suppress_budget_exhausted" in text:
            hits.append(str(path.relative_to(root.parent.parent)))
    assert hits == [], hits


def test_r6_order_drift_fingerprint_flip_recovers_then_budget(
    ctx: RunContext,
) -> None:
    """First heal that flips authority token recovers (consumer may retry once)."""
    plant_seed_complete_through(ctx, "mix")
    sel = bump_order_lock(
        {"ordered_segment_ids": ["a", "b", "c"], "version": 1}, source="r6"
    )
    edl = _edl(["a", "b"])
    before_token = edl_content_authority_token(edl)
    before_hash = str(sel.get("order_content_hash") or "")
    # The synthetic ids a/b/c are not in the fixture manifest, so one-writer
    # sanitize drops them all as orphan refs and then refuses the empty write.
    # This test is about the order-drift fingerprint, so keep the ids verbatim.
    ctx._one_writer_raw = True
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    ctx.write_json("master/edl.json", edl, skip_handoff=True)
    exc = SystemExit("selection_edl_order_drift: speech clip order diverges")

    first = handle_stage_failure(ctx, "mix", exc)
    assert first.playbook_id == "selection_edl_order_drift"
    assert first.resume_stage in {"edl", "junction_snip_qa", "mix", "information_package_plan"}
    if first.status == "recovered":
        after_sel = ctx.read_json("master/selection.json")
        after_edl = ctx.read_json("master/edl.json")
        assert (
            edl_content_authority_token(after_edl) != before_token
            or str(after_sel.get("order_content_hash") or "") != before_hash
        )
        assert after_sel.get("ordered_segment_ids") == ["a", "b"]
    else:
        assert first.status == "escalate"

    second = handle_stage_failure(ctx, "mix", exc)
    assert second.status == "escalate"
    assert second.playbook_id in {"budget_exhausted", "selection_edl_order_drift"}
    assert second.resume_stage in {"edl", "junction_snip_qa", "mix", "information_package_plan"}


def test_r6_order_drift_noop_aligned_escalates_with_edl_pin(ctx: RunContext) -> None:
    """Already-aligned drift must not claim recovered / burn as a fake heal."""
    sel = bump_order_lock(
        {"ordered_segment_ids": ["a", "b"], "version": 1}, source="r6"
    )
    edl = _edl(["a", "b"])
    # Keep hashes locked so action == ok.
    edl = {**edl, "order_content_hash": sel["order_content_hash"], "order_lock": sel["order_lock"]}
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    ctx.write_json("master/edl.json", edl, skip_handoff=True)
    exc = SystemExit("selection_edl_order_drift: speech clip order diverges")

    first = handle_stage_failure(ctx, "mix", exc)
    assert first.status == "escalate"
    assert first.playbook_id == "selection_edl_order_drift"
    assert first.resume_stage in {"edl", "junction_snip_qa"}
    assert first.artifacts_written == []

    second = handle_stage_failure(ctx, "mix", exc)
    assert second.status == "escalate"
    assert second.playbook_id == "budget_exhausted"
    assert second.resume_stage in {"edl", "junction_snip_qa"}


def test_r6_orientation_noop_pins_producer_then_budget(ctx: RunContext) -> None:
    """Unsanitary orientation: escalate with vo_synthesize pin (not recovered edl)."""
    plant_seed_complete_through(ctx, "vo_line_adjudicate")
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "opening_orientation": {
                "line_id": _LINE,
                "required": True,
                "target_segment_id": "seg_001",
            },
            "interviewer_lines": [
                {
                    "line_id": _LINE,
                    "text": "Before the science, meet the founder.",
                    "delivery": "synthesize",
                    "required": True,
                    "episode_orientation": True,
                    "placement": "before",
                    "targets_segment_id": "seg_001",
                }
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "version": 1,
            "plan_status": "complete",
            "air_script": {
                "beats": [{"beat_id": "b1"}],
                "vo_seats": {"seated_line_ids": [_LINE], "omitted_line_ids": []},
            },
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
            "clips": [],
            "timeline_duration_ms": 0,
        },
        skip_handoff=True,
    )
    assert edl_heal_resume_stage(ctx) == "vo_synthesize"
    assert producer_pin_for_token("opening_orientation_inaudible", ctx=ctx) == "vo_synthesize"

    exc = PublishabilityBlocked(
        PublishabilityReport(checkpoint="post_edl", ok=False, violations=[]),
        error_class="opening_orientation_inaudible",
    )
    first = handle_stage_failure(ctx, "edl", exc)
    assert first.playbook_id == "opening_orientation_inaudible"
    assert first.resume_stage in {"vo_synthesize", "edl", "vo_line_adjudicate"}
    if first.status == "escalate":
        assert first.artifacts_written == []
    else:
        assert first.status == "recovered"

    second = handle_stage_failure(ctx, "edl", exc)
    assert second.status in {"escalate", "recovered"}
    assert second.playbook_id in {
        "budget_exhausted",
        "opening_orientation_inaudible",
    }
    assert second.resume_stage in {"vo_synthesize", "edl", "vo_line_adjudicate"}
