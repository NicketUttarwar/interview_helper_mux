# High-risk stage audit — edl_narrative_audit

tier: T0 | seed: #57 | runs_hit: 9/9  
status: `complete`  
mode: rescore  
updated: 2026-09-25T17:09:26Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path: hard inputs present → **prepare** reads transitions + occupancy (no seam mutation; ENA S6) → OpenAI flagship audit → persist `master/edl_narrative_audit.json`. On **fail**: one-shot metadata align (chapters/plan; hard_freeze plan-only) + demote disk-stale blockers — **refuse** if still fail (ENA S7: no remutate / no marker clear / no coverage bind).

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `understanding/content_brief.json`, `master/coverage_audit.json`, `master/narrative_plan.json`, `master/selection.json` | Contract hard |
| Reads (soft) | `sound_design_plan`, `transitions`, `gap_report`, `nle_edits`, `mastering_plan`, VO pickup WAVs | Heard-WAV mode |
| Writes (SSOT) | `master/edl_narrative_audit.json` | Stage primary |
| Soft / side | Fail path may mutate `selection`/`narrative_plan` via `narrative_metadata_align` only; remutate JSON is driver-compat demote-or-refuse | No coverage co-write (S8) |

### Rules that govern it

- **Admit** — persistable audit envelope; hollow done refuses if effective blockers or heard-WAV incomplete
- **Refuse** — leave `verdict=fail` for operator when remutate exhausted / timeline reopen refused; never soft-pass fail
- **Incomplete** — HE-1: `vo_synthesize` not seed-complete or required seated VO missing/stale WAV → resume VO (`edl_narrative:vo_g1` class)
- **Heal** — one-shot metadata align + demotion only; never soft-pass fail; no remutate / marker clear (S7)
- **Wait_for_gate** — none dedicated; depends on G1/VO seed-complete upstream
- **Done / hollow honesty** — `effective_narrative_blocking_issues` + heard_wav incompleteness in `stage_completion`
- **Hard floors / QC bars** — chapter continuity / ordering / seam occupancy live mainly in `edl_narrative_qc` for post-EDL; audit LLM + demotion for pre-EDL
- **Freeze / never_touch / ownership** — ALLOW for `narrative_metadata_align` on selection + narrative_plan under freeze; hard_freeze skips selection rewrite (plan-only). No sanitize/ranking spoofed `stage_key`s (S1)

### Considerations & load-bearing policy

- **Selection is air-order authority** — audit must align plan *down*, never reinclusion leftovers (prompt + repair doctrine).
- **Hard-keeps** must not blank-drop (HEAD guards in `repair_master_selection` / `repair_edl_narrative_selection`); blank hard_keeps stay on-air and demote `blank_segment` blockers.
- **Chapter orphans** demoted when every ordered id is chapter-owned after fill/align.
- **Heard WAV** is load-bearing (clinic ENA-B1 KEEP): audit before VO complete is incomplete, not a narrative fail.
- Sanitize / ranking remain lattice owners; this stage thrashing their artifacts recreates SOS/ranking debt.

### LLM / external calls

- `docs/prompts/selection/edl-narrative-audit.system.txt` via `run_flow_llm_stage` (≤2 attempts / invoke).
- Hollow meaning: `verdict=fail` with live blockers, or missing heard coverage — not a green `.stage_done`.

### What it deliberately does *not* do

- Does not write final `master/edl.json` (consumer: `edl`)
- Does not seal ranking lattice / primary-impact (ranking / sanitize)
- Does not synthesize VO WAVs
- Prompt forbids re-expanding excluded segments to fill empty narrative chapters

### Operator-visible effects

- Fail after demote stays fail for operator / upstream; Full-auto may still see `edl_narrative:vo_g1` when walk reaches audit before VO seed-complete
- No dedicated GUI gate; blocks `edl` via `narrative_audit_blocks_edl` / delivery guardrails

---

## 1. Job statement

Judge whether the **already-selected** air order is narratively ready for EDL (coverage, chapters, seams, heard VO) — refuse or classify repairs; do not reinvent membership.

---

## 2. Error-hint intake

From the high-risk report. Classify each predicate.

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| Chapter orphans / `chapter_continuity_broken` | `root_here` + `still_present_on_HEAD` (partially demoted) | LLM still emits; HEAD demotes when `ordered ⊆ chapter membership` after fill/align. Remutate maps code → `align_plan`. Repair↔sanitize thrash when selection rewritten under foreign keys |
| Blank-drop of **hard_keep** segs → `hard_keep_missing` | `healed` (guard) + residual `authority_friction` | HEAD skips blank-drop for hard_keeps in `repair_master_selection` / `repair_edl_narrative_selection`; demotes blank blockers when on-air ⊆ hard_keep. Historical thrash with sanitize/lattice still shapes remutate `drop_blank` action |
| AuthorityDenied on `narrative_plan.json` (owner=`narrative_arc_plan`) | `authority_friction` | ALLOW rows for `edl_narrative_audit` + `narrative_metadata_align` exist; exec_13198 still showed `authority_denied:persist:master/selection.json:edl_narrative_audit:hard_freeze:j*` — host/repair paths or mutation class mismatch under hard_freeze |
| `edl_narrative:vo_g1` / vo_synthesize not seed-complete | `downstream_of_vo_synthesize` + `seed_order_noise` | HE-1 intentional; dominant forensics on exec_13198 (7×). False narrative blocker if walk reaches audit early |

Report why-high-risk: Chapter orphans, blank hard_keep drop → sanitize thrash

Classification values: `root_here` | `downstream_of_X` | `seed_order_noise` | `authority_friction` | `still_present_on_HEAD` | `healed`

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `stages/edl_narrative_audit.py::run_edl_narrative_audit` |
| Prepare | `prepare_edl_narrative_audit_inputs` — **read-only** transitions + occupancy (`persist=False` if missing); `compact_vo_coverage` / seats |
| Persist + repair | `audit_repair_loop.maybe_repair_after_narrative_audit` (~91 LOC) — metadata align / hard_freeze plan-only + `repair_edl_audit`; **no remutate** |
| Remutate (driver compat) | `edl_narrative_remutate.py` (~811): classify/plan retained; `apply_*` = demote-or-refuse (no marker clear) |
| QC (EDL consumer) | `edl_narrative_qc.validate_flow1_edl_narrative` (~1.0k) — out of stage body job count |
| Selection chapter productize | `repair_edl_narrative_selection` chapter-fill only; ALLOW `narrative_metadata_align` |
| Freeze / ownership | ALLOW selection/narrative_plan `narrative_metadata_align`; one_writer admit passes mutation_class |
| Hollow / gates | `stage_completion` HE-1; `stage_input_checks`; delivery guardrails |
| Tests (non local-ML) | `test_ena_s1_s5_simplify.py`, `test_edl_narrative_remutate.py`, `test_ws3_edl_narrative_disk_gate.py`, `test_i12_narrative_repair_hard_freeze.py` |

---

## 4. Business-logic walk

1. **Happy** — inputs OK, VO seed-complete, LLM `pass`/`warn` → persist audit → edl proceeds.
2. **Incomplete** — VO not seed-complete or required WAV missing/stale → hollow incompleteness (`edl_narrative:vo_g1`); not a narrative craft fail.
3. **Refuse** — after one demote/align, `verdict=fail` left for operator/upstream (no remutate).
4. **Heal (fail path)** — hard_freeze: plan-only; else metadata_align (chapters/plan, no blank-drop) → `repair_edl_audit` demote → stop.
5. **LLM ≤2** — stage invoke cap only (remutate loop removed from persist path).
6. **Done honesty** — effective blockers or heard incompleteness keep stage hollow.

---

## 5. Over-engineering scorecard

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **6+** | (1) LLM audit verdict (2) pre-LLM seam/transition prep (3) post-fail multi-artifact repair (4) remutate classify/plan/apply + stage rewind (5) host_repair VO/layup/orientation (6) disk demotion / hollow honesty; plus QC module family for EDL |
| Dual / competing SSOTs | **yes** | Audit JSON vs `effective_narrative_blocking_issues`; chapters on selection vs narrative_plan; seam_occupancy vs transitions/gap prose; selection writes fingerprint as ranking/sanitize |
| Soft-heal / thrash re-admit loops | **yes** | fail → repair → remutate → clear `.stage_done` → ranking/transitions/VO → re-audit; chapter fill vs sanitize/authority undo historically |
| Co-producer / unpaid land | **yes** | Writes `selection` as `selection_order_sanitize` / `full_master_ranking`; `gap_report` as `gap_framing_compose`; transitions + layup plan from host_repair; narrative_plan co-write |
| Brittle predicates vs simple rules | **yes** | Substring `_CLASSIFIERS` / CHAPTER_OVERFLOW_MARKERS / prose needles for demotion and remutate action pick |
| Disproportionate shard/memo/resume | **yes** | ~2.7k LOC across stage+qc+remutate; remutate memo; run_meta `edl_narrative_audit_repair_done`; host_repair does half of delivery |
| “Fix everything downstream” behavior | **yes** | `_ACTION_STAGES` can rewind ranking, transitions, framing_apply, layup, adjudicate, synthesize |

**Over-engineered?** `yes` — far more than one job; thrash remutate + unpaid multi-artifact land on fail.

**Scorecard verdict:** `FAIL`

- What would flip FAIL → PASS: stage owns **audit + refuse/classify only**; one freeze-honest metadata align (chapters/plan down to selection); no blank membership surgery / no VO-layup host kitchen / no spoofed producer stage_keys; remutate collapsed to pin upstream owner without clearing a half-pipeline.

### 5b — Re-score (MODE=rescore 2026-09-25T17:09:26Z)

HEAD verified: `audit_repair_loop` demote-or-refuse only; prepare read-only; no coverage co-write; 9 smoke tests green; LOC stage 203 / repair 91 / remutate-compat 811.

Hard fail-if: responsibilities ≥3 · dual=yes · soft-heal=yes · unpaid co-producer=yes · brittle=yes · shard=yes · fix-downstream=yes.  
`partial` does **not** trip fail-if.

| Check | Answer | Fail-if? | Evidence on HEAD |
|-------|--------|----------|------------------|
| Responsibilities count | **2** | no | (1) LLM audit (2) one-shot fail metadata-align + demote. Prepare = read-only packet. QC module is EDL consumer |
| Dual / competing SSOTs | **partial** | no | Demotion mutates same audit JSON; `effective_*` still filters for hollow/EDL |
| Soft-heal / thrash re-admit loops | **no** | no | No remutate from persist; no `.stage_done` clear; no `repair_done`; no drop-stale-fail-audit |
| Co-producer / unpaid land | **no** | no | Coverage bind gone; selection/plan only via ALLOW `narrative_metadata_align` |
| Brittle predicates vs simple rules | **partial** | no | Driver/compat classify substring API remains; demotion code-first |
| Disproportionate shard/memo/resume | **partial** | no | Remutate module kept for driver demote-or-refuse; unused classify/plan surface |
| “Fix everything downstream” behavior | **no** | no | Persist path cannot rewind ranking/VO/transitions |

**Fail-if hits:** 0  
**Over-engineered?** `no`  
**Scorecard verdict: PASS**

Prior mid-campaign scores: §5a FAIL (pre-simplify) · post-S1–S5 FAIL (responsibilities=4) · post-S6–S8 PASS (confirmed).

---

## 6. Complexity subtraction list

| id | P | Status | Change | Clears check |
|----|---|--------|--------|--------------|
| S1–S8 | — | **all done** | See prior MODE=fix notes | → PASS |
| B1 | P2 | backlog | Delete uncalled `seed_missing_seated_layups` + unused classify→plan stage maps if driver no longer needs them | shard (partial) |
| B2 | P2 | backlog | Fold `effective_*` into demoted audit-only gate | dual (partial) |

**Open ship rows:** none.  
**Operator decisions recorded:** S3 safest · S4 safest · S7 collapse.

---

## 7. Root-cause verdict

HEAD confirms the stage is a **pre-EDL narrative judge**: read packet → LLM → on fail one align+demote else refuse. Historical thrash (spoof writers, blank-drop, VO kitchen, remutate rewind) is peeled. Optional debt is leftover remutate classify surface for driver compat — not a scorecard fail.

---

## 8. Recommended next action

`leave`

---

## 9. Scope fence

Upstream poison owner (if any): `vo_synthesize` / G1 seating (vo_g1); `full_master_ranking` / `selection_order_sanitize`; `narrative_arc_plan` / hitch  
Downstream victims (names only): `edl`, `junction_snip_qa`, `mix`, `listen_delight_audit`  
Did **not** redesign other stages.
