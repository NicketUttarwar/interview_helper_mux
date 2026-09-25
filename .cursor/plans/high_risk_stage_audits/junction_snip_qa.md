# High-risk stage audit — junction_snip_qa

tier: T2 | seed: #65 | runs_hit: 7/9 + all masters  
status: `complete`  
mode: fix  
updated: 2026-09-25T18:10:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

### What this stage does

Happy path: read live `master/edl.json` → deterministic detectors → optional thought-complete enrich → bounded repair rounds (nudge / cut / merge / omit / music fade via placement) writing NLE + live EDL (+ selection omit) → **critical-only** nested remaster when incomplete cuts need audio → one advisory `junction_feel_audit` LLM (no directive remaster) → commitment remaster if assembly older than EDL → seam autopsy → write `master/junction_snip_qa.json` → loud refuse if critical residuals remain.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `master/edl.json` | Contract hard; skip-done if missing |
| Reads (soft) | selection, assembly.wav, segments, gap_report, SDP, NLE | |
| Writes (SSOT) | `master/junction_snip_qa.json`, `master/junction_feel_audit.json`, `master/junction_thought_complete.json` | Feel advisory-only |
| Co-writes | live EDL, selection omit, NLE, seam_autopsy, render_ledger, placement_adjustments | **No SDP rewrite (S4)** |
| Soft / side | run_meta qc_summaries; `clear_stale_*` when live detect clean | No remediation_run_log / fuse arm from stage |

### Rules that govern it

- **Admit** — speech junctions; music cues lacking soft XF (via placement)
- **Refuse** — outer mix on live incomplete cuts; terminal `junction_quality_blocked` on critical residuals; no nested `run_edl`
- **Incomplete** — commitment must match assembly; mid-flight junction remaster blocks seed via incompleteness (paid for unpaid_land taxonomy — S6(B))
- **Heal** — in-stage EDL/NLE repair + critical/commitment remaster only; **no** severity soften; **no** fuse/hitch arm from run; S6(B) junction-owned remaster is paid land (mix stays unpaid)
- **Wait_for_gate** — re-arms `g_listen_pending` after critical remaster
- **Done / hollow honesty** — autopsy commitment ↔ assembly; orphan promote still refused mid remaster
- **Hard floors** — incomplete_cut kinds hard-block
- **Freeze / ownership** — selection omit ALLOW; SDP never written from junction; junction-owned remaster = paid land

### Considerations & load-bearing policy

- Selection leads order lock; junction may omit only.
- S1 keep: critical repair remaster + commitment remaster (mix cannot own mid-ladder while incomplete refuse stands).
- Clear_stale kept for live-clean stamp reconcile (publishability); severity soften removed.

### LLM / external calls

- thought-complete enrich; feel audit ≤2 (advisory — no apply/remaster)

### What it deliberately does *not* do

- Feel directive remaster / cosmetic `path=repair` remaster
- Nested `run_edl`, SDP crossfade patch, fuse/hitch arming, failure_recovery identify/plan
- Critical→warning severity soften

### Operator-visible effects

- Blocks mix on live incomplete cuts; blocks ship on critical residuals after budget

---

## 1. Job statement

Detect and repair hearable cut defects on the live EDL (especially incomplete mid-thought ends), reseat assembly for critical/commitment paths, and commit a junction autopsy mix/finalize can trust.

---

## 2. Error-hint intake

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `music_hard_transition` | `still_present_on_HEAD` | Placement XF only (S4) |
| `mid_word_*` / silence | `still_present_on_HEAD` | EDL/NLE repair; no cosmetic remaster (S1) |
| incomplete / on_a_roll | `root_here` | Critical remaster + hard refuse |
| `incomplete_cut_unresolved` | `root_here` | Mix refuse via live detect |
| `selection_edl_order_drift` | `authority_friction` | Selection-leads lock |
| AuthorityDenied SDP / sealed | `healed` (S4) | No SDP write |
| Soft residual thrash | `healed` (S3) | No severity soften; clear_stale kept |

Report why-high-risk: Mid-word / silence / music cuts; blocks mix

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry | `junction_snip_qa.py::run_junction_snip_qa` |
| Detectors / repairs | `detect_junction_findings`, `apply_junction_repairs` |
| Remaster | `_budgeted_remaster_mix` — critical + commitment only |
| Feel | `run_junction_feel_audit` advisory; no `apply_feel_directives` in run |
| Tests | `test_jsq_s1_s5_simplify.py` + prior junction suite |

---

## 4. Business-logic walk

1. **Happy** — detect → repair → critical remaster if needed → feel advisory → commitment remaster → autopsy → pass.
2. **Refuse** — critical residuals after rounds; commitment remaster refuse; no speech → RuntimeError (no nested edl).
3. **Heal** — EDL/NLE only for observational; clear_stale external; no fuse arm.
4. **LLM** — thought-complete + feel write-only.
5. **Done honesty** — commitment ↔ assembly.

---

## 5. Over-engineering scorecard

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **5** | Pre-S1–S5 baseline |
| Dual / competing SSOTs | **yes** | Pre-simplify |
| Soft-heal / thrash re-admit loops | **yes** | Pre-simplify |
| Co-producer / unpaid land | **yes** | Pre-simplify |
| Brittle predicates vs simple rules | **yes** | Pre-simplify |
| Disproportionate shard/memo/resume | **yes** | Pre-simplify |
| “Fix everything downstream” behavior | **yes** | Pre-simplify |

**Over-engineered?** `yes`  
**Scorecard verdict:** `FAIL` (baseline §5a)

### 5b — Re-score after changes (leave/monitor 2026-09-25T18:10:00Z)

Operator: **leave/monitor** (no A). Nested critical/commitment remaster is the intentional S1 keep — primary junction job, not thrash co-producer land. HEAD also has S6(B) paid-land carve-out (parallel); mix stays unpaid mid-flight. `test_jsq_s1_s5_simplify.py` + `test_jsq_s6_paid_remaster_land.py` green.

| Check | Answer | Fail-if? | Evidence now |
|-------|--------|----------|--------------|
| Responsibilities count | **2** | no | detect+repair; critical/commitment remaster + refuse |
| Dual / competing SSOTs | **partial** | no | Placement-only; autopsy commitment; clear_stale live-clean |
| Soft-heal / thrash re-admit loops | **no** | no | No feel remaster / soften / fuse arm |
| Co-producer / unpaid land | **no** | no | Remaster is junction-owned seat (S1 keep); unpaid taxonomy does not thrash-land junction; mix remains unpaid mid-flight |
| Brittle predicates vs simple rules | **partial** | no | Detector edge-winners remain (monitor, not fail-if) |
| Disproportionate shard/memo/resume | **partial** | no | Module large; peels hold — leave/monitor |
| “Fix everything downstream” behavior | **no** | no | No nested edl / SDP / fuse; remaster seats own critical repairs |

**Fail-if hits:** 0  
**Over-engineered?** `no`  
**Scorecard verdict:** `PASS`

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | needs_you → **decided: critical+commitment remaster only** | **done:** no cosmetic `path=repair`; no nested `run_edl`; keep critical + commitment remaster | resp; fix-downstream | source + tests |
| S2 | P0 | unambiguous | **done:** feel advisory-only; no `apply_feel_directives` / feel remaster in run | soft-heal thrash | `feel_advisory_only` stamp |
| S3 | P0 | needs_you → **decided: drop soften, keep clear_stale** | **done:** no critical→warning soften; clear_stale unchanged | dual SSOT; brittle | no `critical_residuals_softened` |
| S4 | P1 | unambiguous | **done:** placement_adjustments only; `_patch_sdp_cue_crossfade` no-op | dual SSOT; authority | SDP unchanged after music repair |
| S5 | P1 | needs_you → **decided: loud refuse, peel arming** | **done:** no identify/plan/fuse/hitch/remediation_run_log in run | soft-heal; fix-downstream | source inspect |
| S6 | P1 | needs_you → **decided: leave/monitor** (2026-09-25) | **superseded / done:** operator chose leave/monitor (no A redesign). HEAD already has S6(B) paid-land carve-out from parallel work — leave = no further peels; monitor that carve-out | co-producer / unpaid land | `test_jsq_s6_paid_remaster_land.py` (HEAD); no new cuts |

**Open ship rows:** none.  
**Operator decisions recorded:** S1 critical+commitment; S3 drop soften keep clear_stale; S5 peel arming; **S6 leave/monitor** (accept intentional nested remaster; do not ship A).

**Backlog:** shrink detector surface; delete unused feel/fuse helpers if unused. Monitor: junction paid-land carve-out must not soft-pass mix unpaid mid-flight.

---

## 7. Root-cause verdict

Pre-simplify junction was a kitchen. After S1–S5 (+ intentional remaster ownership / leave-monitor), HEAD is **repair + critical seat + refuse**. Not over-engineered. Scorecard **PASS**.

---

## 8. Recommended next action

`leave`

---

## 9. Scope fence

Upstream poison owner (if any): `edl` / selection incomplete cuts; SDP hard music fades  
Downstream victims (names only): `mix`, `master_finalize`, `listen_delight_audit`  
Did **not** redesign other stages.
