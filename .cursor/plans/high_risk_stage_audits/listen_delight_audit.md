# High-risk stage audit — listen_delight_audit

tier: T2 | seed: #60 | runs_hit: (gate)  
status: `complete`  
mode: fix  
updated: 2026-09-25T17:55:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

### What this stage does

Happy path: after EDL + selection are seated, **score** eight listen-delight dimensions from on-disk artifacts → write `mastering/listen_delight_audit.json` as a **pre_mix advisory** pass → stamp qc_summaries → `heal_or_raise`. Authoritative **ship block** is `master_finalize` → `run_authoritative_listen_delight_at_ship` (post_master). Floor misses remutate via **recovery playbook only** (finite N); stage/`_handle` plans or records advisory — never APPLY / clear `.stage_done`.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `master/edl.json`, `master/selection.json` | Contract hard inputs |
| Reads (soft) | assembly / SDP / delivery_brief; junction, gap_report, plan, seam autopsy, bridge | Dimension evidence |
| Writes (SSOT) | `mastering/listen_delight_audit.json` | Co-ALLOW with `master_finalize` (post_master) |
| Writes (control) | `mastering/listen_delight_remutate.json` | Recovery APPLY / sticky exhaust |
| Soft / side | `run_meta.json` qc_summaries; aspirational candidates | Ops |

### Rules that govern it

- **Admit** — seed walk; Phase-A consumers require delight cleared
- **Refuse** — loud_fail at **ship** when authoritative + aspirational off / catastrophic miss
- **Incomplete** — `listen_delight_incomplete` when audit not cleared for Phase A
- **Heal** — `heal_or_raise` after advisory write; remutate APPLY only in recovery
- **Done honesty** — pre_mix done ≠ ship cleared; `fail_early` knob ignored
- **Hard floors** — per-dim floors; post_master LD1 missing-evidence clamp
- **Freeze / ownership** — audit ALLOW delight + finalize; mix DENY; no selection pack from remutate

### Considerations & load-bearing policy

- NORTH_STAR ship gate; risk was remutate/ownership thrash, not low scores.
- Clinic KEEP: pre_mix advisory + finalize ship re-run.
- Mix no longer rewrites audit (mix S1 + this S2).

### LLM / external calls

N/A for scoring. Homunculus ingest on miss. Remutate APPLY via recovery.

### What it deliberately does *not* do

- APPLY remutate / clear stage markers from stage body
- Pack `master/selection.json`
- Rewrite audit from mix (`rerun_listen_delight_after_mix` is in-memory only)
- Soft-waive floors under authoritative mode at ship

### Operator-visible effects

- Phase-A / music admit incomplete until cleared
- Remutate rewinds only when recovery playbook applies
- Ship: finalize LoudStageFailure `listen_delight_floors_failed` when hard-block

---

## 1. Job statement

Score the seated cut against listen-delight dimension floors and either clear an honest advisory audit or refuse at ship — remutate APPLY belongs to recovery, not this stage body.

---

## 2. Error-hint intake

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `post_master` | `still_present_on_HEAD` | Ship pass phase; often clears |
| Remutate / escalate loops | `healed` (stage) / recovery-owned | Stage no longer APPLY; playbook caps at N |
| AuthorityDenied vs delight under mix | `healed` | Mix DENY + no post_mix write |
| `listen_delight_floors_failed` | `root_here` (ship gate) | Finalize loud fail when hard-block |
| `listen_delight_incomplete` | `still_present_on_HEAD` | Progress gate |

Report why-high-risk: Authoritative ship gate; remutate loops

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `listen_delight.py::run_listen_delight_audit` |
| Ship re-score | `run_authoritative_listen_delight_at_ship` |
| Post-mix (soft) | `rerun_listen_delight_after_mix` — evaluate only, no persist |
| Remutate APPLY | `listen_delight_remutate.apply_*` via `playbook_listen_delight_remutate` |
| Freeze / ownership | audit co-ALLOW finalize; remutate.json this stage |
| Contract | `docs/cross-cutting/stage-contracts/listen_delight_audit.yaml` |
| Tests | `test_listen_delight.py`, `test_lda_s1_s5_simplify.py`, ownership deny |

---

## 4. Business-logic walk

1. **Evaluate** → write pre_mix advisory audit → ingest on miss → `heal_or_raise`.
2. **Ship** → finalize re-scores post_master; `_handle` may pick-best / soft-proceed; remutate skipped_at_ship (no APPLY).
3. **Recovery** → plan+APPLY remutate (gain/seat gates, stage clears, no selection pack).

---

## 5. Over-engineering scorecard

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **5** | baseline pre-fix |
| Dual / competing SSOTs | **yes** | baseline |
| Soft-heal / thrash re-admit loops | **yes** | baseline |
| Co-producer / unpaid land | **yes** | baseline |
| Brittle predicates vs simple rules | **yes** | baseline |
| Disproportionate shard/memo/resume | **partial** | baseline |
| “Fix everything downstream” behavior | **yes** | baseline |

**Over-engineered?** `yes` — baseline.

**Scorecard verdict:** `FAIL` — baseline.

### 5b — Re-score after changes (MODE=fix)

| Check | Answer | Delta | Evidence now |
|-------|--------|-------|--------------|
| Responsibilities count | **2** | −3 | Score + persist/refuse envelope; APPLY peeled to recovery |
| Dual / competing SSOTs | **no** | cleared | Mix post_mix gone; finalize co-ALLOW is intentional ship pass |
| Soft-heal / thrash re-admit loops | **no** | cleared | Stage/`_handle` never APPLY / clear `.stage_done` |
| Co-producer / unpaid land | **no** | cleared | Selection pack removed; mix DENY locked |
| Brittle predicates vs simple rules | **partial** | eased | fail_early branch deleted; 8 dims frozen (not collapsed) |
| Disproportionate shard/memo/resume | **no** | eased | Remutate ledger recovery-owned |
| “Fix everything downstream” behavior | **no** | cleared | APPLY only via playbook |

**Over-engineered?** `no` — ≤2 responsibilities; no hard fail-if `yes` rows (brittle residual is partial only).

**Scorecard verdict:** `PASS`

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | needs_you | **done** | `done:` `_handle` + stage never call `apply_*`; deferred_to_recovery | Soft-heal; fix-everything; responsibilities | `test_lda_s1_s5_simplify.py::test_s1_*` |
| S2 | P0 | needs_you | **done** | `done:` `rerun_listen_delight_after_mix` evaluate-only (no `write_json` / AUDIT_REL) | Dual SSOT | `test_s2_*` (+ mix already deleted call) |
| S3 | P0 | unambiguous | **done** | `done:` removed selection pack from `apply_listen_delight_remutate` | Co-producer unpaid | `test_s3_*` |
| S4 | P1 | needs_you | **done** | `done:` safest — delete fail_early blocking branch; knob ignored | Responsibilities; brittle | `test_s4_*` + `test_fail_early_knob_ignored_*` |
| S5 | P1 | unambiguous | **done** | `done:` contract comment + ownership pins (mix DENY; delight+finalize ALLOW) | Dual SSOT | `test_s5_*` |

Operator decisions (2026-09-25): **all safest** — S1 peel APPLY; S2 demote post_mix (no persist); S3 no selection pack; S4 delete fail_early (not collapse dims); S5 ownership/contract assert.

Open rows: none (PASS). Optional backlog: collapse 8 dims → fewer floors if operators want thinner rubric.

---

## 7. Root-cause verdict

S1–S5 landed. Stage is advisory score+write; ship gate stays at finalize; remutate APPLY is recovery-only; no unpaid selection land; mix cannot rewrite audit SSOT.

---

## 8. Recommended next action

`leave` — scorecard **PASS** after S1–S5. Do not add heal layers.

---

## 9. Scope fence

Upstream poison owner (if any): junction residuals / mix seat / ranking retention.  
Downstream victims (names only): `mix`, `master_finalize`, `mmaudio_sfx` / Phase-A, `podcast_publish`.  
Did **not** redesign other stages.
