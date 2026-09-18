"""Seed↔contract alignment ratchet (0.2.0 leapfrog footgun)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_audit():
    path = ROOT / "tools" / "audit_seed_contract_alignment.py"
    name = "audit_seed_contract_alignment"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_audit_flags_topology_content_context_soft_underdeclare():
    """D14 thrash class must stay visible until SEED_ORDER promote lands."""
    mod = _load_audit()
    findings = mod.audit()
    forbidden = [
        f
        for f in findings
        if f.producer == "source_topology_build" and f.consumer == "content_context"
    ]
    # After promote, this should be empty; while soft, must fail closed.
    from interview_mux.stage_contract import load_contract

    c = load_contract("content_context")
    assert c is not None
    topo_hard = any(
        d.hard and d.path == "understanding/source_topology.json" for d in c.inputs
    )
    if topo_hard:
        assert not forbidden
    else:
        assert forbidden, "topology→content_context soft under-declare must be flagged"


def test_audit_script_exit_matches_findings():
    mod = _load_audit()
    findings = mod.audit()
    code = mod.main([])
    assert code == (1 if findings else 0)


def test_content_context_soft_review_queue_not_duplicated() -> None:
    """CC-B2: review_queue appears once via transcript_quality_reads, not twice."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("content_context")
    assert c is not None
    soft_rq = [
        d.path for d in c.inputs if not d.hard and d.path == "transcript/review_queue.json"
    ]
    assert soft_rq == ["transcript/review_queue.json"]


def test_narrative_arc_plan_contract_hard_coverage_and_brief() -> None:
    """NAP-B1: hard inputs match `_check_narrative_arc_plan` (coverage + brief)."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("narrative_arc_plan")
    assert c is not None
    hard = {d.path for d in c.inputs if d.hard and d.path}
    soft = {d.path for d in c.inputs if not d.hard and d.path}
    assert "master/coverage_audit.json" in hard
    assert "understanding/content_brief.json" in hard
    assert "understanding/content_brief.json" not in soft


def test_full_master_ranking_contract_hard_matches_input_checks() -> None:
    """FMR-B1: hard inputs track `_check_full_master_ranking`, not fuse/coverage."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("full_master_ranking")
    assert c is not None
    hard = {d.path for d in c.inputs if d.hard and d.path}
    soft = {d.path for d in c.inputs if not d.hard and d.path}
    assert hard == {
        "master/narrative_plan.json",
        "segments/manifest.json",
        "understanding/gap_report.json",
    }
    assert "analysis/connector_fuse_rounds.json" in soft
    assert "master/coverage_audit.json" in soft
    assert "analysis/connector_fuse_rounds.json" not in hard
    assert "master/coverage_audit.json" not in hard


def test_nugget_corpus_mine_contract_honesty() -> None:
    """NCM-B1/B3: corpus only output; mastering_plan soft; selection hard.
    NCM-B2: sufficiency documents nuggets min_rows≥1."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("nugget_corpus_mine")
    assert c is not None
    outs = {o.path for o in c.outputs}
    hard = {d.path for d in c.inputs if d.hard and d.path}
    soft = {d.path for d in c.inputs if not d.hard and d.path}
    assert outs == {"understanding/nugget_corpus.json"}
    assert "understanding/nugget_layup_qc.json" not in outs
    assert "master/selection.json" in hard
    assert "mastering/mastering_plan.json" in soft
    assert "mastering/mastering_plan.json" not in hard
    rules = [r for r in (c.sufficiency or []) if getattr(r, "path", None) == "nuggets"]
    assert rules and int(rules[0].min_count or 0) >= 1


def test_nugget_layup_compose_contract_hard_selection_corpus_audit_soft() -> None:
    """NLC-B3: hard = selection+corpus; IP audit soft (shadow enrichment)."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("nugget_layup_compose")
    assert c is not None
    hard = {d.path for d in c.inputs if d.hard and d.path}
    soft = {d.path for d in c.inputs if not d.hard and d.path}
    assert hard == {
        "master/selection.json",
        "understanding/nugget_corpus.json",
    }
    assert "mastering/shape/information_packages_audit.json" in soft
    assert "mastering/shape/information_packages_audit.json" not in hard


def test_refinement_agenda_contract_gap_report_soft() -> None:
    """RA-B1: gap_report soft; hard:[]; body never refuses on missing report."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("refinement_agenda")
    assert c is not None
    hard = {d.path for d in c.inputs if d.hard and d.path}
    soft = {d.path for d in c.inputs if not d.hard and d.path}
    assert hard == set()
    assert "understanding/gap_report.json" in soft
    assert "understanding/gap_report.json" not in hard


def test_transitions_contract_hard_matches_payload() -> None:
    """Stage Clinic transitions-B2: brief+gap hard with selection (payload reads)."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("transitions")
    assert c is not None
    hard = {d.path for d in c.inputs if d.hard and d.path}
    soft = {d.path for d in c.inputs if not d.hard and d.path}
    assert "master/selection.json" in hard
    assert "understanding/content_brief.json" in hard
    assert "understanding/gap_report.json" in hard
    assert "understanding/content_brief.json" not in soft
    assert "understanding/gap_report.json" not in soft


def test_transitions_b1_empty_ok_min_rows_zero() -> None:
    """Clinic transitions-B1: empty transitions OK — sufficiency min_rows 0 (no drift)."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("transitions")
    assert c is not None
    rules = [r for r in (c.sufficiency or []) if getattr(r, "path", None) == "transitions"]
    assert rules, "expected transitions sufficiency rule"
    assert rules[0].rule == "min_rows"
    assert int(rules[0].min_count or 0) == 0


def test_vo_synthesize_contract_hard_includes_transitions() -> None:
    """Stage Clinic VS-B2: hard inputs = gap_report + transitions (not gap-only)."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("vo_synthesize")
    assert c is not None
    hard = {d.path: d.producer for d in c.inputs if d.hard and d.path}
    assert hard.get("understanding/gap_report.json") == "gap_framing_compose"
    assert hard.get("master/transitions.json") == "transitions"


def test_sound_design_vo_finalize_contract_hard_includes_sdp() -> None:
    """Stage Clinic SDVF-B2: hard inputs = vo_synthesize + sound_design_plan."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("sound_design_vo_finalize")
    assert c is not None
    hard = {d.path: d.producer for d in c.inputs if d.hard and d.path}
    assert hard.get("mastering/vo_synthesize.json") == "vo_synthesize"
    assert hard.get("understanding/sound_design_plan.json") == "sound_design_plan"


def test_edl_narrative_audit_contract_hard_matches_payload() -> None:
    """Stage Clinic ENA-B2: hard = brief+coverage+narrative+selection; consumers edl."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("edl_narrative_audit")
    assert c is not None
    hard = {d.path: d.producer for d in c.inputs if d.hard and d.path}
    soft = {d.path for d in c.inputs if not d.hard and d.path}
    assert hard.get("understanding/content_brief.json") == "content_context"
    assert hard.get("master/coverage_audit.json") == "topic_coverage_audit"
    assert hard.get("master/narrative_plan.json") == "narrative_arc_plan"
    assert hard.get("master/selection.json") == "full_master_ranking"
    assert "understanding/sound_design_plan.json" not in hard
    assert "understanding/sound_design_plan.json" in soft
    assert c.consumers == ["edl"]


def test_edl_contract_sdp_soft_producer_is_delivery_plan() -> None:
    """Stage Clinic EDL-B2: soft SDP producer = sound_design_plan (not palettes)."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("edl")
    assert c is not None
    soft = {d.path: d.producer for d in c.inputs if not d.hard and d.path}
    assert soft.get("understanding/sound_design_plan.json") == "sound_design_plan"


def test_mastering_research_waves_contract_has_no_hard_routing() -> None:
    """MRW-B1 / CSP-02: waves never hard-gates on routing.json."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("mastering_research_waves")
    assert c is not None
    hard_paths = {d.path for d in c.inputs if d.hard and d.path}
    assert "mastering/research/routing.json" not in hard_paths
    assert hard_paths == set()


def test_mastering_research_rollup_contract_has_no_hard_waves() -> None:
    """CSP-02: rollup re-probes; never hard-gates on waves.json."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("mastering_research_rollup")
    assert c is not None
    hard_paths = {d.path for d in c.inputs if d.hard and d.path}
    assert "mastering/research/waves.json" not in hard_paths
    assert hard_paths == set()


def test_assembly_preview_contract_selection_soft() -> None:
    """Stage Clinic AP-B2: hard = edl only; selection unused by run_preview → soft."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("assembly_preview")
    assert c is not None
    hard = {d.path: d.producer for d in c.inputs if d.hard and d.path}
    soft = {d.path: d.producer for d in c.inputs if not d.hard and d.path}
    assert hard == {"master/edl.json": "edl"}
    assert soft.get("master/selection.json") == "full_master_ranking"
    assert "master/selection.json" not in hard
    assert "ingest/normalized.wav" in soft


def test_junction_snip_qa_contract_selection_soft_correctness() -> None:
    """Stage Clinic JSQ-B4: hard = edl only; selection soft+correctness (matches `_check`)."""
    from interview_mux.stage_contract import load_contract

    c = load_contract("junction_snip_qa")
    assert c is not None
    hard = {d.path for d in c.inputs if d.hard and d.path}
    soft_sel = next(
        (d for d in c.inputs if (not d.hard) and d.path == "master/selection.json"),
        None,
    )
    assert hard == {"master/edl.json"}
    assert soft_sel is not None
    assert soft_sel.correctness is True


def test_forbidden_pairs_never_on_allowlist():
    mod = _load_audit()
    for pair in mod.FORBIDDEN_SOFT_UNDERDECLARE:
        assert pair not in mod.CONSECUTIVE_SOFT_ALLOWLIST
