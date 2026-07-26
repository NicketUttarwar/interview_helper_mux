"""Deterministic mastering hardening compilers: context, diversity, feasibility,
semantic integrity, pareto.

Specs: docs/cross-cutting/mastering-quality-hardening.md and siblings.
"""

from __future__ import annotations

import pytest

from interview_mux.mastering_context_compiler import (
    compile_packet,
    make_item,
    provenance_complete,
)
from interview_mux.mastering_diversity import build_diversity_report, candidate_distance
from interview_mux.mastering_feasibility import build_feasibility_report, eligible_candidates
from interview_mux.mastering_pareto import build_frontier, dominates, select_synthesize_inputs
from interview_mux.mastering_semantic_integrity import (
    build_integrity_report,
    clean_candidates,
    flagged_windows,
    merge_llm_findings,
)
from mastering_quality_corpus import (
    TAXONOMY,
    candidates,
    feasibility_inputs,
    fixture_ids,
    integrity_inputs,
    load_fixture,
)

# --- corpus ---------------------------------------------------------------


def test_corpus_covers_every_axis_value():
    seen: dict[str, set[str]] = {axis: set() for axis in TAXONOMY}
    for fid in fixture_ids():
        fixture, _ = load_fixture(fid)
        for axis, value in (fixture.get("tags") or {}).items():
            seen.setdefault(axis, set()).add(value)
    gaps = {
        axis: sorted(set(values) - seen.get(axis, set()))
        for axis, values in TAXONOMY.items()
        if set(values) - seen.get(axis, set())
    }
    assert not gaps, f"eval corpus is missing fixtures for: {gaps}"


# --- context compiler -----------------------------------------------------


def test_packet_stays_inside_token_budget_and_records_omissions():
    items = [
        make_item(ref=f"artifact/{i}.json", kind="artifact", salience=1.0 - i / 10, inline="x" * 400)
        for i in range(10)
    ]
    packet = compile_packet(consumer_id="critic_x", items=items, max_tokens=200)
    assert packet["budget"]["used_tokens"] <= 200
    assert packet["omitted"], "over-budget items must be recorded, not silently dropped"
    assert all(o["ref"] for o in packet["omitted"])


def test_packet_keeps_highest_salience_first():
    items = [
        make_item(ref="low.json", kind="artifact", salience=0.1, inline="y" * 400),
        make_item(ref="high.json", kind="artifact", salience=0.9, inline="z" * 400),
    ]
    packet = compile_packet(consumer_id="critic_x", items=items, max_tokens=110)
    assert packet["items"][0]["ref"] == "high.json"


def test_packet_hashes_every_inlined_item():
    packet = compile_packet(
        consumer_id="field_x",
        items=[make_item(ref="a.json", kind="artifact", salience=1.0, inline={"k": "v"})],
    )
    assert not provenance_complete(packet)


def test_oversized_inline_becomes_a_pointer_with_its_hash():
    packet = compile_packet(
        consumer_id="field_x",
        items=[make_item(ref="big.json", kind="artifact", salience=1.0, inline="q" * 50000)],
        inline_max_chars=100,
    )
    item = packet["items"][0]
    assert item["inline"] is None
    assert item["sha256"]
    assert item["truncated"]


# --- diversity ------------------------------------------------------------


def test_identical_candidates_have_zero_distance():
    cand = {
        "candidate_id": "a",
        "ordered_segment_ids": ["s1", "s2", "s3"],
        "cold_open": {"kind": "none"},
        "thesis_framing": "t",
        "ending_kind": "reflective",
        "speaker_balance": 0.5,
    }
    per_axis = candidate_distance(cand, {**cand, "candidate_id": "b"})
    assert all(v == 0.0 for v in per_axis.values())


def test_near_clone_candidates_trigger_remint():
    base = {
        "candidate_id": "a",
        "ordered_segment_ids": ["s1", "s2", "s3"],
        "cold_open": {"kind": "none"},
        "thesis_framing": "t",
        "ending_kind": "reflective",
        "speaker_balance": 0.5,
    }
    report = build_diversity_report([base, {**base, "candidate_id": "b"}])
    assert report["verdict"] == "remint_required"
    assert report["remint_candidate_ids"] == ["b"]
    assert report["remint_directives"], "remint must name the collapsed axes"


def test_genuinely_different_candidates_pass():
    a = {
        "candidate_id": "a",
        "ordered_segment_ids": ["s1", "s2", "s3"],
        "cold_open": {"kind": "none"},
        "thesis_framing": "one",
        "ending_kind": "reflective",
        "speaker_balance": 0.2,
        "target_duration_ms": 600000,
    }
    b = {
        "candidate_id": "b",
        "ordered_segment_ids": ["s4", "s5"],
        "cold_open": {"kind": "segment_hook"},
        "thesis_framing": "two",
        "ending_kind": "punchline",
        "speaker_balance": 0.9,
        "target_duration_ms": 3600000,
        "sfx_cue_refs": ["c1", "c2", "c3", "c4", "c5"],
    }
    assert build_diversity_report([a, b])["verdict"] == "pass"


# --- feasibility ----------------------------------------------------------


@pytest.mark.parametrize("fixture_id", fixture_ids())
def test_feasibility_matches_corpus_expectations(fixture_id: str):
    fixture, expectations = load_fixture(fixture_id)
    report = build_feasibility_report(candidates(fixture), feasibility_inputs(fixture))
    for candidate_id, expected in (expectations.get("feasibility") or {}).items():
        row = next(c for c in report["candidates"] if c["candidate_id"] == candidate_id)
        if expected == "fail":
            assert row["verdict"] == "fail", f"{fixture_id}/{candidate_id}: {row}"
        else:
            assert row["verdict"] != "fail", f"{fixture_id}/{candidate_id}: {row['blocking_reasons']}"


def test_feasibility_blocks_split_locked_volley():
    from interview_mux.mastering_feasibility import FeasibilityInputs

    inputs = FeasibilityInputs(
        segments={s: {"start_ms": 0, "end_ms": 1000} for s in ("s1", "s2", "s3")},
        locked_volleys=[["s1", "s2"]],
    )
    report = build_feasibility_report(
        [{"candidate_id": "a", "ordered_segment_ids": ["s1", "s3"]}], inputs
    )
    assert report["candidates"][0]["verdict"] == "fail"
    assert any("volley" in r for r in report["candidates"][0]["blocking_reasons"])


def test_feasibility_allow_list_only_applies_when_authoritative():
    fixture, _ = load_fixture("technical_1on1_landmined")
    cands = candidates(fixture)
    advisory = build_feasibility_report(cands, feasibility_inputs(fixture))
    assert len(eligible_candidates(advisory, cands)) == len(cands)

    authoritative = build_feasibility_report(
        cands,
        feasibility_inputs(fixture),
        cfg={"mastering": {"quality_hardening": {"feasibility": {"mode": "authoritative"}}}},
    )
    assert len(eligible_candidates(authoritative, cands)) < len(cands)


# --- semantic integrity ---------------------------------------------------


@pytest.mark.parametrize("fixture_id", fixture_ids())
def test_integrity_catches_seeded_landmines(fixture_id: str):
    fixture, expectations = load_fixture(fixture_id)
    report = build_integrity_report(candidates(fixture), integrity_inputs(fixture))
    found = {
        (c["candidate_id"], f["class_id"], f.get("segment_id"))
        for c in report["candidates"]
        for f in c["findings"]
    }
    for expected in expectations.get("expected_findings") or []:
        key = (expected["candidate_id"], expected["class_id"], expected.get("segment_id"))
        classes = {(cid, cls) for cid, cls, _ in found}
        assert (expected["candidate_id"], expected["class_id"]) in classes, (
            f"{fixture_id}: missed {key}; found {sorted(found)}"
        )


@pytest.mark.parametrize("fixture_id", fixture_ids())
def test_integrity_avoids_false_positive_traps(fixture_id: str):
    fixture, expectations = load_fixture(fixture_id)
    report = build_integrity_report(candidates(fixture), integrity_inputs(fixture))
    found = {
        (c["candidate_id"], f["class_id"])
        for c in report["candidates"]
        for f in c["findings"]
    }
    for trap in expectations.get("must_not_flag") or []:
        key = (trap["candidate_id"], trap["class_id"])
        assert key not in found, f"{fixture_id}: false positive {key}"


def test_integrity_warnings_carry_repair_directives():
    fixture, _ = load_fixture("technical_1on1_landmined")
    report = build_integrity_report(candidates(fixture), integrity_inputs(fixture))
    warns = [
        f
        for c in report["candidates"]
        for f in c["findings"]
        if f["severity"] == "warn"
    ]
    assert warns
    assert all(f.get("repair_directive") for f in warns)


def test_llm_confirm_can_clear_a_deterministic_flag():
    fixture, _ = load_fixture("technical_1on1_landmined")
    report = build_integrity_report(candidates(fixture), integrity_inputs(fixture))
    assert flagged_windows(report)
    cleared = merge_llm_findings(report, [])
    assert cleared["llm_confirm_applied"] is True
    assert all(c["verdict"] == "pass" for c in cleared["candidates"])


def test_critical_findings_only_remove_candidates_when_authoritative():
    fixture, _ = load_fixture("technical_1on1_landmined")
    cands = candidates(fixture)
    advisory = build_integrity_report(cands, integrity_inputs(fixture))
    assert len(clean_candidates(advisory, cands)) == len(cands)

    authoritative = build_integrity_report(
        cands,
        integrity_inputs(fixture),
        cfg={"mastering": {"quality_hardening": {"semantic_integrity": {"mode": "authoritative"}}}},
    )
    assert len(clean_candidates(authoritative, cands)) < len(cands)


# --- pareto ---------------------------------------------------------------


def test_dominance_requires_strictly_better_somewhere():
    dims = ["a", "b"]
    assert dominates({"a": 0.9, "b": 0.5}, {"a": 0.8, "b": 0.5}, dims)
    assert not dominates({"a": 0.8, "b": 0.5}, {"a": 0.8, "b": 0.5}, dims)
    assert not dominates({"a": 0.9, "b": 0.1}, {"a": 0.8, "b": 0.5}, dims)


def test_frontier_keeps_candidates_that_lead_on_one_dimension():
    frontier = build_frontier(
        [
            {"candidate_id": "balanced", "dimension_scores": {"arc": 0.6, "hook": 0.6}},
            {"candidate_id": "spiky", "dimension_scores": {"arc": 0.3, "hook": 0.95}},
            {"candidate_id": "weak", "dimension_scores": {"arc": 0.2, "hook": 0.2}},
        ]
    )
    ids = {m["candidate_id"] for m in frontier["frontier"]}
    assert ids == {"balanced", "spiky"}
    assert [d["candidate_id"] for d in frontier["dominated"]] == ["weak"]


def test_frontier_never_starves_synthesize():
    frontier = build_frontier([{"candidate_id": "only", "dimension_scores": {"arc": 0.4}}])
    assert frontier["frontier"]


def test_synthesize_selection_only_narrows_when_authoritative():
    survivors = [
        {"candidate_id": "a", "dimension_scores": {"arc": 0.9}},
        {"candidate_id": "b", "dimension_scores": {"arc": 0.1}},
    ]
    cands = [{"candidate_id": "a"}, {"candidate_id": "b"}]
    advisory = build_frontier(survivors)
    assert len(select_synthesize_inputs(advisory, cands)) == 2

    authoritative = build_frontier(
        survivors, cfg={"mastering": {"quality_hardening": {"pareto": {"mode": "authoritative"}}}}
    )
    assert [c["candidate_id"] for c in select_synthesize_inputs(authoritative, cands)] == ["a"]
