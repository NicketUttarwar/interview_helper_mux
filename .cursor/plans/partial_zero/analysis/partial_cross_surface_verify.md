# Partial cross-surface verify — HEAD

**Verified:** 2026-09-21  
**HEAD tip (short):** `e7658ccab` (working tree may include later uncommitted patches; checks below are filesystem SSOT)  
**Mode pin:** brain 0.2.0 · partially_accelerated  
**Source catalog:** [cross_surface_gaps_report.md](../cross_surface_gaps_report.md) implement targets P0–P1  

## Coverage table

| Target | Decided solution | HEAD evidence | Tests | Status vs target |
|--------|------------------|---------------|-------|------------------|
| **P0-2 / B-6** `g_listen_mode` warn | Default `warn` fleet-wide; finalize non-blocking | `config/app.defaults.json` → `"g_listen_mode": "warn"`; `gates.require_g_listen_clear` fallback `"warn"`; docs/operator-gates.md say warn | `tests/test_g_listen_full_auto_clear.py::test_default_g_listen_mode_is_warn` | **covered** |
| **H-1** nested synth skip-not-stamp | Partial never auto_accept; skip mint when ladder open | `gap_vo_gates.nested_synth_may_mint`; callers `stages/assembly.py` resync + `transition_vo.resync_spoken_transitions` | `tests/test_nested_synth_skip.py` | **covered** |
| **X-3** narrative QC soft unattended | `is_unattended_run` (Partial + Full-auto); Manual strict | `gates.check_narrative_qc` uses `operator_gates.is_unattended_run` | `test_narrative_qc_partial_softens_strict_fail`, `test_narrative_qc_full_auto_softens_strict_fail` | **covered** |
| **F-2** classify-before-registry | Live helpers before PLAYBOOK_REGISTRY on identical-halt resume | `recovery_controller.live_identical_halt_resume_stage` (high_gap / edl / fuse helpers → registry cold fallback); used from identical-halt path ~L1412 | `tests/test_f2_live_identical_halt_resume.py` | **covered** |

## Verdict

**All four implement targets are covered on HEAD.** No Decision Packet `DP-CROSS-SURFACE` opened.

P2 hygiene from the same catalog (defaults inventory Partial column, transition sidecar cascade, ownership sidecar audit, Partial readiness addendum) is outside this verify set; clinic files already mention warn / unattended soft — treat as soak/hygiene, not a cross-surface implement gap for these four.

## Notes (non-gaps)

- `resume_stage_for_error_class` / other registry lookups remain cold maps by design; F-2 scoped fix is identical-halt live-first.
- G-Listen `block` remains an operator opt-in; default path is warn.
- Nested mint skip defers WAV demand to G1 / `vo_synthesize` / mix — intentional Partial posture.
