"""Every pipeline stage belongs to exactly one operator phase — zero orphans.

Guards the P0 precondition of `.cursor/plans/solver_brain_020.plan.md` §3.1: a
phase-keyed migration plan is only sound if the phases cover the pipeline.
"""

from __future__ import annotations

from collections import Counter

from interview_mux.v2 import phases as P
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

SEED_ORDER = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)


def test_seed_order_is_72_stages():
    assert len(SEED_ORDER) == 72
    assert len(set(SEED_ORDER)) == 72


def test_every_stage_maps_to_exactly_one_phase():
    counts = Counter(P.all_phase_stage_ids())
    duplicated = sorted(s for s, n in counts.items() if n > 1)
    assert duplicated == [], f"stages claimed by more than one phase: {duplicated}"

    orphans = sorted(s for s in SEED_ORDER if s not in counts)
    assert orphans == [], f"stages mapped to no phase: {orphans}"

    unknown = sorted(s for s in counts if s not in set(SEED_ORDER))
    assert unknown == [], f"phase stages absent from the seed order: {unknown}"


def test_phase_for_stage_resolves_every_stage_and_gate():
    for stage_id in SEED_ORDER:
        phase = P.phase_for_stage(stage_id)
        assert phase is not None, stage_id
        assert stage_id in (phase.get("stages") or [])
    for gate in ("transcript_review", "g1_vo_pickup", "g_publish"):
        assert P.phase_for_stage(gate) is not None, gate


def test_previously_orphaned_stages_are_adopted():
    expected = {
        "audio_probe_build": "prepare",
        "framing_posture_decide": "understand-b",
        "selection_order_sanitize": "plan_rank",
        "gap_report_sanitize": "plan_rank",
        "air_contract_sanitize": "plan_rank",
    }
    for stage_id, phase_id in expected.items():
        phase = P.phase_for_stage(stage_id)
        assert phase is not None and phase["id"] == phase_id, stage_id


def test_understand_split_preserves_legacy_id_and_membership():
    split = [p["id"] for p in P.PHASES if p.get("legacy_id") == "understand"]
    assert split == ["understand-a", "understand-b", "understand-c"]

    legacy = P.phase_stage_ids("understand")
    assert legacy == P.phase_stage_ids("understand-a") + P.phase_stage_ids(
        "understand-b"
    ) + P.phase_stage_ids("understand-c")
    assert legacy[0] == "source_acoustic_profile"
    assert P.phase_stage_ids("understand-a")[-1] == "segment_classification"
    assert P.phase_stage_ids("understand-b")[0] == "content_brief_reanchor"
    assert P.phase_stage_ids("understand-b")[-1] == "connector_fuse_pass"
    assert P.phase_stage_ids("understand-c")[0] == "sonic_context_build"
    assert legacy[-1] == "mastering_plan_synthesize"


def test_phase_ids_are_unique_and_phase_stage_lists_follow_seed_order():
    ids = [p["id"] for p in P.PHASES]
    assert len(ids) == len(set(ids))

    index = {s: i for i, s in enumerate(SEED_ORDER)}
    for phase in P.PHASES:
        positions = [index[s] for s in (phase.get("stages") or [])]
        assert positions == sorted(positions), phase["id"]


def test_phase_stage_ranges_do_not_interleave():
    """Phases are contiguous slices of the seed order — a phase is a cut-point."""
    index = {s: i for i, s in enumerate(SEED_ORDER)}
    spans = [
        (min(index[s] for s in stages), max(index[s] for s in stages))
        for phase in P.PHASES
        if (stages := phase.get("stages") or [])
    ]
    spans.sort()
    for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
        assert next_start == prev_end + 1


def test_phases_for_unknown_id_is_empty():
    assert P.phases_for_id("nope") == []
    assert P.phase_stage_ids("nope") == []
