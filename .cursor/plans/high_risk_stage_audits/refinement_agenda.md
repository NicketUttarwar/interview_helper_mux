# High-risk stage audit — refinement_agenda

tier: T1 | seed: #47 | runs_hit: 6/9  
status: `complete`  
mode: rescore  
updated: 2026-09-25T18:00:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path (seed walk + API default `phase="confirm"`): refuse if a **present** `gap_report.json` is W1-unsanitary → detect tape characters from topology / gap_evaluations / acoustic duration → resolve a policy pack’s default eligible Pass-2 classes → priors bias only if explicitly enabled (default **off**, S3) → confirm may inject `ranking` when coverage holes exist; mastering_plan may inject `cold_open` → clamp to vocab → write `understanding/refinement_agenda.json` → ledger first_pass call → `heal_or_refuse_mark(..., force=True)`. Empty eligible (e.g. `simple_tape_override`) is a valid complete outcome.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (soft) | `understanding/gap_report.json` | Present+dirty → refuse; missing soft (RA-B1) |
| Reads (soft) | `understanding/source_topology.json`, `gap_evaluations.json`, `source_acoustic_profile.json` | Tape character |
| Reads (soft) | `master/coverage_audit.json`, `mastering/mastering_plan.json` | Confirm ranking / cold_open inject |
| Writes (SSOT) | `understanding/refinement_agenda.json` | Sole product of this stage |
| Soft / side | refinement ledger via `record_call` | Operational; not agenda body |

**Ownership note (S1 shipped):** `refinement_plan.json` → `gap_framing_recompose` + `selection_framing_apply`; `refinement_cascade.json` → `gap_framing_recompose`; `refinement_ensemble_lint.json` → `ops` (test-only writer; no seed-walk land).

### Rules that govern it

- **Admit** — After `gap_report_sanitize` in seed order (`delivery_guardrails`); soft inputs may be absent
- **Refuse** — Present dirty gap (`gap_unsanitary — resume gap_report_sanitize`)
- **Incomplete** — Missing agenda sidecar (`_pass2_hollow_incompleteness`); empty eligible still complete
- **Heal** — Force mark_done after successful write only
- **Wait_for_gate** — N/A (no operator gate)
- **Done / hollow honesty** — Artifact present = done; empty classes OK by design; no contentful Pass-2 claim
- **Hard floors / QC bars** — None beyond vocab clamp + unsanitary block
- **Freeze / never_touch / ownership** — Sole ALLOW writer for agenda.json; does not mutate gap_report / selection

### Considerations & load-bearing policy

- **L0 compiler only** — Downstream `refinement_gate.decide_pass` + Pass-2 stages consume eligibility; whitelist/blacklist/simple_tape can still skip even when agenda lists a class
- **Full-auto** — Always runs confirm; empty agenda is intentional for short_clean packs
- **Upstream** — Looks hot in forensics when layup / sanitize / ranking seed-order stalls (report pattern with #49 / #46)
- **Publishability** — Indirect: wrong empty eligible can starve recomposes; wrong non-empty only opens gates that still decide activate|skip

### LLM / external calls

N/A — deterministic. Priors module remains opt-in (`analysis.refinement_passes.priors.enabled`); Full-auto defaults leave it off.

### What it deliberately does *not* do

- Does not recompose gap VO / apply framing excludes / refine ranking or transitions
- Does not write `refinement_plan` / cascade / ensemble lint (ALLOW re-homed S1)
- Does not sanitize gap_report or own selection membership

### Operator-visible effects

- No dedicated GUI gate; refinement summary routes may read agenda
- Seed-order errors surface on **downstream** stages (“complete refinement_agenda before…”) when this stage never landed

---

## 1. Job statement

Compile which Pass-2 refinement **classes** are eligible for this tape into `understanding/refinement_agenda.json` (or honestly refuse while present gap is unsanitary).

---

## 2. Error-hint intake

From the high-risk report. Classify each predicate.

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| Seed-order pile-up behind layup / ranking | `seed_order_noise` / `downstream_of_nugget_layup_compose` | Report groups #47 with #49/#46; real root often unpaid layup / dirty gap_report |
| `stage_error` “complete refinement_agenda before selection_framing_apply” (exec_13198 peek) | `seed_order_noise` | Victim is SFA; agenda never completed because upstream chain stalled |
| Hollow / empty eligible still done | `healed` (by design) | Clinic thrash_hotspot; target + RA-B* accept empty complete |
| gap_unsanitary refuse | `still_present_on_HEAD` | RA-B2 intentional honesty — not over-eng |

Report why-high-risk: Seed-order pile-up behind layup / ranking

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `src/interview_mux/refinement_agenda.py::run_refinement_agenda` |
| Key helpers | `_gap_unsanitary_block`; `refinement_policy.detect_tape_character` / `resolve_policy_pack`; `refinement_priors.bias_eligible_classes`; `refinement_ledger.record_call` |
| Primary writes | `understanding/refinement_agenda.json` via `ctx.write_json` |
| Freeze / ownership | `artifact_ownership` ALLOW agenda only; plan/cascade/ensemble re-homed (S1) |
| Done / incomplete | `stage_completion._pass2_hollow_incompleteness` (agenda exists); `heal_or_refuse_mark(..., force=True)` |
| Dispatch | `pipeline.py` → `phase="confirm"`; API default now `confirm` (S2); `draft` test-only |
| Contract | `docs/cross-cutting/stage-contracts/refinement_agenda.yaml` |
| Tests (non local-ML) | `test_refinement_core.py`; `test_ra_s1_s3_simplify.py` |

---

## 4. Business-logic walk

1. **Preflight** — If gap_report exists and `gap_sanitary_errors` non-empty → `RuntimeError` (no write, no done). Missing gap: soft continue.
2. **Character + pack** — Topology substrings / high-gap / jargon / duration bands → pack_id (`short_clean` may zero eligible via `simple_tape_override`).
3. **Bias / inject** — Soft priors opt-in only (S3 default off); confirm+coverage holes append `ranking` even under simple_tape (RA-B3); mastering cold_open may append `cold_open`.
4. **Persist** — Eligible + ineligible + succession_hints + optional mastering_bind → agenda.json.
5. **Ledger** — Best-effort `record_call` (swallow RuntimeError).
6. **Done** — Force heal if not already done. No LLM attempts. Default phase `confirm` (S2); `draft` remains explicit/test-only.

---

## 5. Over-engineering scorecard

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **2** | (1) decide eligible classes for tape; (2) persist agenda / refuse dirty gap. No Pass-2 apply, no multi-artifact land. |
| Dual / competing SSOTs | **no** | Single product SSOT `refinement_agenda.json`. Gate whitelist is consumer policy, not a second agenda writer. Ghost ALLOW for plan/cascade/ensemble ≠ dual product SSOT. |
| Soft-heal / thrash re-admit loops | **no** | One force mark after successful write; unsanitary refuses without stamp. No re-admit / remutate loop in body. |
| Co-producer / unpaid land | **no** | Writes only agenda.json; does not thrash-land gap_report/selection. |
| Brittle predicates vs simple rules | **partial** | Topology string heuristics remain; prior-rate bias off by default (S3). Done rule still simple (file exists). |
| Disproportionate shard/memo/resume | **no** | ~130-line body; no shards/resume theater. |
| “Fix everything downstream” behavior | **no** | Emits eligibility list + hints only; gate/passes own activate\|skip and mutations. |

**Over-engineered?** `no` — ≤2 responsibilities; no hard fail-if rows (brittle is partial only).

**Scorecard verdict:** `PASS`

- Ledger heat is seed-order reflection of layup/sanitize failures, not stage bloat.
- What would flip FAIL → PASS: N/A (already PASS).

### 5b — Re-score after changes (MODE=rescore · HEAD 2026-09-25)

Re-read: `refinement_agenda.py` (confirm default, priors gated), ownership rows for plan/cascade/ensemble, `refinement_catalog` / `app.defaults` priors off, `tests/test_ra_s1_s3_simplify.py` green (5).

| Check | Answer | Delta vs §5a | Evidence now |
|-------|--------|--------------|--------------|
| Responsibilities count | **2** | — | Decide eligible classes; persist / refuse dirty gap. Still one product SSOT. |
| Dual / competing SSOTs | **no** | cleared ghost ALLOW | Agenda sole product path; plan/cascade/ensemble producers are GFR/SFA/ops — not this stage. |
| Soft-heal / thrash re-admit loops | **no** | — | Single force mark after write; unsanitary raises before persist. |
| Co-producer / unpaid land | **no** | — | Writes only `refinement_agenda.json`. |
| Brittle predicates vs simple rules | **partial** | softer (priors off) | Topology/duration pack heuristics remain; prior-rate expand off by default. Not fail-if `yes`. |
| Disproportionate shard/memo/resume | **no** | — | Thin body; no shard/resume theater. |
| “Fix everything downstream” behavior | **no** | — | Eligibility + hints only. |

**Over-engineered?** `no` — responsibilities ≤2; zero hard fail-if rows (`partial` brittle alone does not flip Over-eng).  
**Scorecard verdict:** `PASS`

No FAIL fail-if hits → no new §6 open cuts required.

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P2 | decided: re-home to real stage writers | **done** | plan→GFR+SFA; cascade→GFR; ensemble→ops | ownership hygiene | `test_ra_s1_s3_simplify.py::test_s1_*` |
| S2 | P3 | decided: confirm default + draft test-only | **done** | default=`confirm`; draft kept for RA-B3 | dead default path | `test_s2_default_phase_is_confirm` |
| S3 | P3 | decided: disable priors by default (module kept) | **done** | defaults + catalog `enabled: false` | adjacent bloat | `test_s3_priors_disabled_by_default` |

Open rows: none (scorecard PASS — leave / monitor).

Backlog (not opened): peel unused `draft` API entirely; delete priors module if never opted in — both `needs_you`, non-blocking.---

## 7. Root-cause verdict

**Not the root of the high-risk heat.** Report predicates are almost entirely **seed-order pile-up** when `#45 nugget_layup_compose` / gap sanitize / hitch / ranking stall; HEAD forensics show downstream stages blaming “complete refinement_agenda before…”. Stage body is a thin L0 eligible-class compiler with intentional empty-complete and RA-B2 unsanitary refuse. Residual risk (OPEN_RISK in failure catalog) is **policy correctness** (simple_tape emptying classes while gate skips recomposes) — product judgment, not over-engineering.

---

## 8. Recommended next action

`leave` (rescore PASS; S1–S3 shipped; no open cuts)

---

## 9. Scope fence

Upstream poison owner (if any): `nugget_layup_compose` / `gap_report_sanitize` (and hitch/ranking when they block sanitize land)  
Downstream victims (names only): `gap_framing_recompose`, `selection_framing_apply`, later Pass-2 consumers via gate  
Did **not** redesign other stages.
