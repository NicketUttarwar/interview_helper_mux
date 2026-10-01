"""Blank fragments never reach the committed air order; order-derived documents follow it (ISSUES 115).

exec_084: a 3-second, 7-word fragment was ranked onto air, the EDL rendered
it, the EDL gate's repair then dropped it from the selection under the hard
freeze and failed its own parity check; the narrative plan's constraint over
that fragment made the sound design plan refuse; the episode structure went
stale and its rewrite was refused for ownership.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.selection_dependents import reconcile_selection_dependents
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment, write_fixture_json


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "blank_order")


LONG = " ".join(["word"] * 40)


def _manifest(ctx) -> None:
    write_fixture_json(
        ctx,
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_001", start_ms=0, end_ms=20_000, speaker_id="spk_0", text=LONG),
            minimal_manifest_segment("seg_004", start_ms=30_000, end_ms=50_000, speaker_id="spk_0", text=LONG),
            minimal_manifest_segment("seg_005", start_ms=60_000, end_ms=80_000, speaker_id="spk_0", text=LONG),
            minimal_manifest_segment(
                "seg_007", start_ms=356_730, end_ms=359_970, speaker_id="spk_0", text="Okay? Where the sensitivity, the specific"
            ),
        ),
    )


def test_a_blank_fragment_is_excluded_by_selection_order_sanitize(ctx) -> None:
    from interview_mux.air_order_boundary import drop_blank_segments
    from interview_mux.artifact_repairs import _segment_is_blank_or_unusable

    _manifest(ctx)
    assert _segment_is_blank_or_unusable(ctx, "seg_007") is True
    doc = {"ordered_segment_ids": ["seg_001", "seg_004", "seg_005", "seg_007"], "chapters": []}
    out = drop_blank_segments(ctx, doc)
    assert out["ordered_segment_ids"] == ["seg_001", "seg_004", "seg_005"]
    assert any(
        (r.get("segment_id") if isinstance(r, dict) else r) == "seg_007" for r in out.get("excluded_segment_ids") or []
    )
    # The sanitize stage is the one place that applies it before the freeze.
    import interview_mux.artifact_sanitize.selection as stage_mod

    src = Path(stage_mod.__file__).read_text(encoding="utf-8")
    body = src[src.index("def run_selection_order_sanitize") :]
    assert 0 < body.index("drop_blank_segments(") < body.index("commit_selection_mutation(")


def test_contradicting_narrative_constraints_are_rewritten_to_the_committed_order(ctx) -> None:
    from interview_mux.order_reconcile import material_order_conflicts

    _manifest(ctx)
    write_fixture_json(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_001", "seg_004", "seg_005"]})
    from run_fixtures import minimal_narrative_plan

    plan = minimal_narrative_plan(
        ordering_constraints=[
            {"before_segment_id": "seg_005", "after_segment_id": "seg_004", "reason": "contradicts the order"},
            {"before_segment_id": "seg_001", "after_segment_id": "seg_004", "reason": "fine"},
        ]
    )
    p = ctx.final_path("master", "narrative_plan.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    import json

    p.write_text(json.dumps(plan), encoding="utf-8")
    assert material_order_conflicts(["seg_001", "seg_004", "seg_005"], plan)
    current = ctx.read_json("master/selection.json")
    notes = reconcile_selection_dependents(ctx, producer="full_master_ranking", previous=current, current=current)
    assert any(n.startswith("narrative_constraints_rewritten") for n in notes), notes
    after = ctx.read_json("master/narrative_plan.json")
    assert material_order_conflicts(["seg_001", "seg_004", "seg_005"], after) == []


def test_the_episode_structure_is_rebuilt_under_its_owner_when_the_order_changes(ctx, monkeypatch) -> None:
    import interview_mux.episode_structure as es

    _manifest(ctx)
    write_fixture_json(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_001", "seg_004", "seg_005"]})
    sp = ctx.final_path("understanding", "episode_structure.json")
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text('{"segment_order": ["seg_001", "seg_007", "seg_004", "seg_005"]}', encoding="utf-8")
    seen: dict = {}
    monkeypatch.setattr(es, "structure_enabled", lambda cfg=None: True)
    monkeypatch.setattr(es, "build_episode_structure", lambda c, *, refresh=False: {"segment_order": ["seg_001", "seg_004", "seg_005"]})

    def _persist(c, doc, *, stage, stage_key=None):
        seen.update({"doc": doc, "stage": stage, "stage_key": stage_key})

    monkeypatch.setattr(es, "persist_structure", _persist)
    notes = reconcile_selection_dependents(
        ctx,
        producer="edl_narrative_audit",
        previous={"ordered_segment_ids": ["seg_001", "seg_007", "seg_004", "seg_005"]},
        current={"ordered_segment_ids": ["seg_001", "seg_004", "seg_005"]},
    )
    assert "episode_structure_refreshed" in notes, notes
    assert seen["stage_key"] == "episode_structure_compose"
    assert seen["doc"]["segment_order"] == ["seg_001", "seg_004", "seg_005"]


def test_structure_is_not_rebuilt_when_the_order_is_unchanged(ctx, monkeypatch) -> None:
    import interview_mux.episode_structure as es

    _manifest(ctx)
    write_fixture_json(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_001", "seg_004"]})
    monkeypatch.setattr(es, "build_episode_structure", lambda c, *, refresh=False: pytest.fail("rebuilt"))
    current = ctx.read_json("master/selection.json")
    notes = reconcile_selection_dependents(ctx, producer="x", previous=current, current=current)
    assert "episode_structure_refreshed" not in notes
