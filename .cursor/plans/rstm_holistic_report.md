# Residual risk catalog — implementation status

**Updated:** 2026-09-09 (Wave 9 footgun closure complete)  
**Sources:** Wave-A failure catalog + Wave-B RSTM + residual cluster hardening + wave_9_footgun_closure plan  
**Out of scope (unchanged):** STT/diarization, MusicGen/MMAudio, DeepFilterNet, Chatterbox execution.

---

## Already fixed (prior + Wave 8 + Wave 9)

| ID | Status |
|----|--------|
| PATCHED-01 empty `{}` | Done (prior) |
| PATCHED-02 committed master | Done (prior) |
| A-01 | **Wave 9:** shape-core (W1–3) thin refuse for Shape/gap consumers under defaults (no LLM-flag gate) |
| A-02..A-05 | Done; **A-03 Wave 9:** soft_gate never authoritative `complete`; bind requires `plan_status=complete`; LLM flags stay off |
| B-01..B-07 | Done; **B-06 Wave 9:** combined clear_from forbidden; heals via profiles + archive_allowlist; AST lint |
| C-01..C-05 | Done; **C-05 Wave 9:** Phase-A seal requires layup `seed_stage_complete` only (no file-exists escape) |
| D-01..D-08 | Done; **D-02 Wave 9:** `advanceFromCheckpoint` choke-point (Partial+driver refresh-only) |
| E-01..E-05 | Done |
| F-01..F-07 | Done; **F-02/F-03 Wave 9:** fail-visible ledger + invent-last finalize; **F-06:** ghosts non-dispatchable |
| G-01..G-03 | Done |

---

## Wave 9 footgun closures (complete)

| Item | Fix | Proof |
|------|-----|-------|
| A-03 | soft_gate → degraded only; hybrid bind needs `complete` | `test_a03_*` defaults |
| A-01 | shape-core thin refuse without flags | `test_narrative_excellence` / residual hardening |
| F-03 | `_finalize_policy` invent last | `test_f03_operator_override_cannot_bypass_*` |
| D-02 | AppContext continue choke | `gateAdvance.test.ts` |
| F-02 | fail-visible vernacular cascade | `test_f02_*` inject |
| B-06 | no combined clear; profiles | `test_b06_clear_from_allowlist.py` |
| C-05 | seal seed_complete-only | `test_delivery_guardrails` seal tests |
| F-06 | `RETIRED_REFINE_GHOSTS` | `test_f06_retired_refine_ghosts.py` |
| SSOT + F-01/04/05 | `critical_residual_view` + behavioral | `test_residual_wave9.py` |

Verify: **153** focused pytest + **75** GUI vitest green (2026-09-09).

---

## Six-gap closure (post Wave 8)

| Gap | Proof |
|-----|-------|
| A-03 Shape/research LLM wire | `tests/test_a03_mastering_llm_cutover.py` — flags default false |
| F-02 shadow must_keep | `tests/test_residual_six_gaps.py::test_f02_*` + scorecard smoke |
| F-03 invent gate | `tests/test_residual_six_gaps.py::test_f03_*` + schema `invent_gate` |
| B-02/B-03 residual visibility | `record_delivery_residual` + `test_b02_*` / `test_b03_*` |
| RSTM Done-when scorecard | `tests/rstm/residual_cluster_scorecard.py` (RC-DW) |
| SDP admit thrash | raw scaffold + empty-hash progress exception + `exec_*` test ids |

---

## Wave 9 — residual SSOT + behavioral proofs

| Item | Status |
|------|--------|
| `CriticalResidualView` / `critical_residual_view` / `has_critical_residuals` | Done — unions ledger + junction `residual_findings` + stamped ints |
| `ship_path_ready` | Uses `has_critical_residuals` (reason preserves ledger vs junction) |
| Junction terminal stamp | `critical_residual_count` + `critical_residuals` (+ `critical_count`) |
| Mirror | Appends synthetic `residual_findings` entry when junction exists |
| PMQ / publishability / delight cut_integrity | Consume SSOT |
| F-01 behavioral | `test_residual_wave9.py::test_f01_*` (string-only retired) |
| F-04 behavioral | cfg under auto + compose raise + hollow seats incompleteness |
| F-05 behavioral | sdp_placeholders / none / legacy_fallback trio |
| B-02 SSOT | ledger blocks ship+PMQ+publishability; findings alone via view |
| Dilution | **DW-09** ship ≡ PMQ ≡ publishability ≡ delight on critical count |

Primary suite: `tests/test_residual_wave9.py`.

---

## Wave 8 Done-when proofs (RC-DW)

Registry: `tests/rstm/residual_cluster_scorecard.py` · gate: `pytest tests/rstm/test_residual_cluster_scorecard.py -q`

| ID | Primary proof |
|----|---------------|
| A-01 | shape-core thin refuse under defaults (`test_narrative_excellence` / residual hardening) |
| A-02 | `test_artifact_completeness.py::test_a02_hollow_primary_arrays_incompleteness` |
| A-03 | soft_gate never complete under defaults — `test_a03_mastering_llm_cutover.py` |
| A-04 | `test_delivery_guardrails.py::test_a04_*` (+ residual hardening) |
| A-05 | `test_shared_path_authority.py::test_a05_*` |
| B-01 | `test_residual_cluster_cb.py::test_b01_*` |
| B-02 | fuse finite + six_gaps + `test_residual_wave9.py::test_b02_ssot_*` |
| B-03 | `FAMILY_JUNCTION` in HALT + `test_b03_*` + junction budget exhaust |
| B-04 | `test_residual_cluster_cb.py::test_b04_*` |
| B-05 | `test_residual_cluster_cb.py::test_b05_*` |
| B-06 | unknown profile + `test_b06_clear_from_allowlist.py` |
| B-07 | `test_residual_cluster_cb.py::test_b07_*` |
| C-01 | `test_residual_cluster_cb.py::test_c01_*` |
| C-02 | `test_residual_cluster_cb.py::test_c02_*` |
| C-03 | `test_delivery_thrash_hardening.py::test_may_rewind_c03_*` |
| C-04 | `test_residual_cluster_cb.py::test_c04_*` |
| C-05 | VO seed_complete + Wave 9 seal seed_complete-only tests |
| D-01 | `partialAcceleratedGuard.test.ts` + `test_partial_auto_mode.py` SSOT |
| D-02 | AppContext choke — `gateAdvance.test.ts` |
| D-03 | `gateAdvance.test.ts` mutator guard suite |
| D-04 | `test_full_auto_launch_api.py::test_create_run_refuses_when_driver_already_running` |
| D-05 | inline `smoke_d05_*` + `test_premature_cap_pins_not_advances` |
| D-06 | `test_partial_auto_mode.py` G0 skip + G-Publish consent |
| D-07 | `test_recommended_framing_honors_llm_no_and_sparse` |
| D-08 | `test_premature_cap_heal_exception_never_falls_to_consumer` |
| E-01..E-05 | `test_cluster_e_hardening.py::test_e0*` |
| F-01 | `test_residual_wave9.py::test_f01_quality_eval_exception_skips_boundary_write` |
| F-02 | `test_residual_six_gaps.py::test_f02_*` + smoke |
| F-03 | `test_residual_six_gaps.py::test_f03_*` + smoke |
| F-04 | `test_residual_wave9.py::test_f04_*` (+ smoke secondary) |
| F-05 | `test_residual_wave9.py::test_f05_*` (+ smoke secondary) |
| F-06 | inline `smoke_f06_refine_stage_retired` |
| F-07 | inline `smoke_f07_*` + `test_write_staging.py::test_read_path_ignores_other_stage_incomplete_pending` |
| G-01 | `resolveReviewGate.test.ts` |
| G-02 | `qcSummaryState.test.ts` |
| G-03 | inline `smoke_g03_*` + `preclean.test.ts` |

**Dilution watch (9):** A-01, A-03, A-04, C-05, D-01, F-02, F-03, B-02(/B-03), **DW-09 residual SSOT** — parents stay closed with behavioral proofs (not string-only).

---

## Verify notes

- Wave 9 suite: `pytest tests/test_residual_wave9.py tests/test_residual_six_gaps.py tests/rstm/test_residual_cluster_scorecard.py -q`
- Six-gap suite remains green with SSOT ship path.
- A-03 flags remain **default false**; `consumers_bind` stays false.
- SDP: empty scaffold writes via `_one_writer_raw`; empty→harden is not authority-undo thrash.
