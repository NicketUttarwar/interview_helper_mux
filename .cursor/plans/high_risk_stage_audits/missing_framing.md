# High-risk stage audit — missing_framing

tier: T0 | seed: #30 | runs_hit: 6/9  
status: `complete`  
mode: rescore  
updated: 2026-09-25T17:05:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

### What this stage does

Happy path (G-Framing Yes + eligible): require `mastering/mastering_plan.json` → restamp span speakers → shard live manifest ids into LLM volleys (`OA-07`) → merge by `segment_id` → `_coverage_loop` spends one `coverage_passes` ledger on unscored leftovers then sealed/risk re-volleys (CAP=2) → terminal **seal-or-refuse** (never batch_fill writes) → persist `understanding/gap_evaluations.json` + coverage_report → heal + read-only completeness assert.

Skip path: `ensure_gap_fill_skipped` stamps skip evals only; `ensure_gap_report_skipped` (compose-owned) writes empty `gap_report` + interviewer script.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `segments/manifest.json`, `understanding/content_brief.json`, `mastering/mastering_plan.json`, `segments/boundaries.json` | Plan absence = loud-fail before shards |
| Reads (soft) | speakers, topology, talking_points, spine/coherence, value_features, narrative priors, VO partner contexts | Rescue pick is risk-first; soft gap_report/selection deps removed (S4) |
| Writes (SSOT) | `understanding/gap_evaluations.json` | Sole producer |
| Soft / side | `understanding/stage_runs/missing_framing/coverage_report.json`, llm_calls globs | Telemetry only |

### Rules that govern it

- **Admit** — G-Framing Yes + gap path clear + mastering plan + eligible (else skip)
- **Refuse** — missing plan; ineligible without auto-skip; empty proactive shard after retry; hard `needs.rerun_stage`; role_tape / starved_host preflight; mid-CAP unscored without budget (`_terminal_seal_unscored`)
- **Incomplete** — `coverage_thin` before CAP; `sealed_ratio_hard` after CAP; stale ids; high without mission; vo_path ladder (distinct UX). Legacy batch_fill only until admit re-entry (S8 seals)
- **Heal** — `_coverage_loop` within CAP; CAP seal; admit-time legacy fill seal; no budget grace
- **Wait_for_gate** — G-Framing / pickup / voice-ref ladder before admit
- **Done / hollow honesty** — seals keep-eligible after CAP; skip producer allows done; S8 clears fills on next MF admit
- **Hard floors** — scored_ratio ~0.95; sealed_ratio_max 0.15 / hard_max 0.35
- **Freeze / ownership** — owns gap_evaluations; DENY on gap_report / interviewer_script; flow_adaptation co-own for gate metadata

### Considerations & load-bearing policy

- First gap-path LLM after framing Yes; does not synthesize VO.
- Thin CAP seals can still starve compose → high_gap; mission incompleteness is local guard.
- Full-auto: one coverage ledger bounds resume; no batch_fill walk-door.

### LLM / external calls

OA-07 `missing-framing.system.txt`; ≤2 attempts per shard empty-retry; coverage passes share stage identity.

### What it deliberately does *not* do

- Does not write VO copy into `gap_report` (compose / `ensure_gap_report_skipped`)
- Does not choose G-Framing; does not lock selection; does not synthesize WAV

### Operator-visible effects

- Incomplete `coverage_thin` / `sealed_ratio_hard` / vo_path pin resume here
- Coverage report under `understanding/stage_runs/missing_framing/`

---

## 1. Job statement

LLM-score every live manifest segment for interviewer-gap need into `understanding/gap_evaluations.json` so later VO compose and ranking see honest severity/gap_type (or an explicit skip stub when framing is off).

---

## 2. Error-hint intake

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `missing_framing batch_fill` | `healed` (producer) + `still_present_on_HEAD` (legacy disk) | Producer never writes new fills (S1); incompleteness kept for old artifacts |
| Budget / `dispatch_cap` + batch_fill grace | `healed` | `missing_framing_batch_fill` exemption **removed** |
| Superseded fill duplicates | `healed` | Last-wins incompleteness |
| AuthorityDenied vs topology / boundaries | `authority_friction` | gap_evaluations sole owner; MF DENY on gap_report (S3) |
| Thrash on incomplete fills | `healed` | Stack collapsed; wrong-keep revisit peeled (S6) |
| Propagates `high_gap` | `downstream_of_X` + `root_here` (thin seals) | CAP seals still under-inform VO |

Report why-high-risk: batch_fill incompleteness, budget door, propagates high_gap

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Pipeline admit / skip | `pipeline._run_missing_framing_stage` |
| Entry `run_*` | `stages/gaps.py::run_missing_framing` |
| Payload / shards | `_missing_framing_payload`, `_run_id_shards` |
| Coverage honesty | `_coverage_loop`, `_terminal_seal_unscored`, `_seal_coverage_exhausted_leftovers`, `_coverage_rescue_exhausted` |
| Risk / revisit | `resolve_framing_risk_segment_ids`, `_sealed_vs_risk_ids`, `_wrong_keep_revisit_ids`, `_pick_sealed_ratio_rescue_ids` (risk-first) |
| Skip | `ensure_gap_fill_skipped` (evals) + `ensure_gap_report_skipped` (compose) |
| Done honesty | `stage_completion._missing_framing_*` (+ vo_ladder) |
| Completeness assert | `_assert_gap_evaluations_complete` (read-only) |
| Ownership | gap_evaluations→MF; gap_report/script→compose |
| Contract / prompt | `docs/cross-cutting/stage-contracts/missing_framing.yaml`; `missing-framing.system.txt` |
| Tests | `test_hg3_missing_framing_batch.py`, `test_p15_budget_door.py`, `test_gaps_skip.py`, `test_pipeline_gap_skip_e2e.py` |

---

## 4. Business-logic walk

**Happy:** shard → merge → coverage_loop finds nothing to do → persist → heal done.

**Coverage:** while `extra_used < CAP`: score unscored, else sealed/risk re-volley; stamp passes.

**Terminal:** leftover after CAP → seal; leftover with budget remaining → refuse (no fill).

**Skip:** evals via MF; report/script via compose helper; mark gap-family done.

**Refuse / incomplete:** plan missing; empty proactive shard; hard needs; sealed_ratio / sealed_vs_risk / legacy fill / mission / vo_ladder.

---

## 5a — Over-engineering scorecard (baseline, pre S1–S5)

| Check | Answer |
|-------|--------|
| Responsibilities count | **6+** |
| Dual / competing SSOTs | **partial** |
| Soft-heal / thrash re-admit loops | **yes** |
| Co-producer / unpaid land | **partial** |
| Brittle predicates vs simple rules | **yes** |
| Disproportionate shard/memo/resume | **yes** |
| “Fix everything downstream” behavior | **partial** |

**Over-engineered?** `yes`  
**Scorecard verdict:** **FAIL**

---

## 5b — Re-score after changes (S1–S8 on HEAD)

| Check | Answer | Evidence | Fail-if? |
|-------|--------|----------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **2** | (1) score+shard (2) one coverage ledger (seal-or-refuse + sealed/risk coverage_thin). S6 peeled wrong-keep revisit | no |
| Dual / competing SSOTs | **no** | Sole `gap_evaluations`; compose owns skip report/script | no |
| Soft-heal / thrash re-admit loops | **no** | No fill→budget thrash; no wrong-keep re-open; `_coverage_loop` is bounded product coverage, not thrash re-admit | no |
| Co-producer / unpaid land | **no** | MF DENY gap_report/script | no |
| Brittle predicates vs simple rules | **no** | S7: one `coverage_thin` pre-CAP + `sealed_ratio_hard` post-CAP; S8 admit-seals legacy fills | no |
| Disproportionate shard/memo/resume | **partial** | Shards still justified for long tapes; no separate rescue/budget grace | no |
| “Fix everything downstream” behavior | **partial** | CAP seals can still thin-feed compose | no |

**Fail-if hits:** 0  
**Over-engineered?** `no`  
**Scorecard verdict:** **PASS**

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status / Change | Clears check | Acceptance hint |
|----|---|------------------------|-----------------|--------------|-----------------|
| S1 | P0 | unambiguous | **done:** CAP seal-or-refuse; no new batch_fill; budget exemption removed | soft-heal / shard / thrash | Producer path seal-or-refuse only |
| S2 | P0 | unambiguous | **done:** sealed_ratio in `_coverage_loop` same CAP ledger | shard / thrash | One `coverage_passes` counter |
| S3 | P1 | unambiguous | **done:** `ensure_gap_report_skipped` compose-owned | dual SSOT / co-producer | MF DENY gap_report |
| S4 | P1 | needs_you → **chose risk-first** | **done:** risk-first pick; soft gap_report/selection deps removed from contract | dual SSOT | Contract matches payload |
| S5 | P2 | unambiguous | **done:** assert read-only (no repair write) | thrash | Assert never mutates SSOT |
| S6 | P0 | unambiguous | **done:** MF never calls `_wrong_keep_revisit_ids` / no keep re-open; coverage_loop owns sealed_vs_risk only | **responsibilities** | responsibilities ≤ 2 |
| S7 | P1 | needs_you → **chose safest** | **done:** one `coverage_thin` resume pre-CAP (ratio ∪ sealed_vs_risk); keep `sealed_ratio_hard` STOP after CAP only | brittle | Single soft predicate; hard_max preserved |
| S8 | P2 | unambiguous | **done:** admit `_promote_legacy_batch_fills_to_seals` + immediate write | brittle leftover | Fresh MF run clears batch_fill incompleteness |

No open subtraction rows. Backlog (monitor): vo_ladder incompleteness UX pin; CAP seals → high_gap downstream.

---

## 7. Root-cause verdict

Baseline was coverage-honesty inflation. S1–S8 collapse it to **score + one coverage ledger**, with compose-owned skip stubs and admit-time legacy fill seals. Scorecard **PASS**. Residual product risk is thin CAP seals feeding high_gap — owned downstream / mission incompleteness, not MF over-engineering.

---

## 8. Recommended next action

`leave` — scorecard PASS; monitor CAP-seal → high_gap if compose still starves.

---

## 9. Scope fence

Upstream poison owner (if any): sparse LLM shards; G0/role_tape; mastering_plan absence  
Downstream victims (names only): `gap_framing_compose`, `optimal_questions`, `full_master_ranking`, `nugget_layup_compose`, high_gap heal path  
Did **not** redesign other stages.
