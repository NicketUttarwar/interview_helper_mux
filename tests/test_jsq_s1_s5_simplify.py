"""junction_snip_qa S1–S5 simplify: critical+commitment remaster, feel advisory, no soften/SDP/heal arm."""

from __future__ import annotations

import inspect

from interview_mux import junction_snip_qa


def test_jsq_s1_no_nested_run_edl_in_remaster() -> None:
    src = inspect.getsource(junction_snip_qa.remaster_mix_only)
    assert "assembly.run_edl" not in src
    assert "refuse nested" in src or "run_edl" in src


def test_jsq_s1_no_cosmetic_repair_remaster_path() -> None:
    src = inspect.getsource(junction_snip_qa.run_junction_snip_qa)
    assert 'path="repair"' not in src
    assert "repair_incomplete_clause" in src
    assert 'path="commitment"' in src or "path=\"commitment\"" in src or "commitment" in src


def test_jsq_s2_feel_advisory_no_directive_remaster() -> None:
    src = inspect.getsource(junction_snip_qa.run_junction_snip_qa)
    assert "apply_feel_directives" not in src
    assert 'path="feel"' not in src
    assert "feel_advisory_only" in src


def test_jsq_s3_no_critical_severity_soften() -> None:
    src = inspect.getsource(junction_snip_qa.run_junction_snip_qa)
    assert "critical_residuals_softened" not in src
    assert "e2e_softened" not in src
    assert "critical_residuals_may_soften" not in src


def test_jsq_s4_placement_only_no_sdp_write() -> None:
    merge_src = inspect.getsource(junction_snip_qa._merge_placement_adjustments)
    assert "_patch_sdp_cue_crossfade" not in merge_src
    patch_src = inspect.getsource(junction_snip_qa._patch_sdp_cue_crossfade)
    assert "write_committed_json" not in patch_src
    assert "sound_design_plan.json" not in patch_src


def test_jsq_s5_no_fuse_hitch_or_failure_recovery_in_run() -> None:
    src = inspect.getsource(junction_snip_qa.run_junction_snip_qa)
    assert "identify_all_failures" not in src
    assert "plan_all_fixes" not in src
    assert "append_learning" not in src
    assert "arm_incomplete_cut_producer_heals" not in src
    assert "arm_hitch_listen_restage" not in src
    assert "run_connector_fuse_pass_junction_heal" not in src
    assert "remediation_run_log.json" not in src
