# High-risk stage audit — full_master_ranking

tier: T0 | seed: #40 | runs_hit: 9/9  
status: `complete`  
mode: rescore  
updated: 2026-09-25T17:09:30Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path: hard inputs present (`narrative_plan`, `segments/manifest`, `gap_report`) → optional STT lexicon pre-scan + specialists → OpenAI ranks segments → persist: topo/NLE/pack → **one** order bind (ideal_cuts seed XOR Shape) → hook/open-shape → **inject lattice keeps** → finalize (CTA cannot drop enforceable primary-impact) → cover manifest orphans → **single seal** → commit selection. Post-commit sides (bridges / story_health refresh / SDP / gap VO rebudget) live on `selection_order_sanitize` via `ensure_ranking_side_artifacts` (FMR S6).

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `master/narrative_plan.json`, `segments/manifest.json`, `understanding/gap_report.json` | `_check_full_master_ranking` |
| Reads (soft) | coverage_audit, content/delivery briefs, episode_structure, fuse rounds, NLE, ideal_cuts seed, mastering_plan, STT boosts, transitions, spine, … | Contract soft list trimmed (S5); many attach-only |
| Writes (SSOT) | `master/selection.json` | Membership + order authority; co-written later by sanitize / framing_apply / remutate |
| Soft / side | `master/rank_candidates.json`, `master/story_health.json` (finalize QC write), `mastering/media_ip_cta.json`, `analysis/stt_lexicon_islands.json`, `operator/ranking_glue_pin.json` | Bridges / SDP / gap VO rebudget → sanitize (S6) |

### Rules that govern it

- **Admit** — persistable envelope (`ordered_segment_ids` ≥ 1); lattice seal clean; pre-flush resilience pass
- **Refuse** — empty ordered; `selection_lattice_seal_refused` (primary-impact / hard_keep residuals); `air_order_integrity` criticals when `block_ranking_on_critical`; narrative_qc.strict fail before LLM
- **Incomplete** — heal pins ranking for `never_exclude_primary_impact` / `framing:primary impact` / hard_keep / integrity criticals; soft pre-flush refuse (`heal_success:pre_flush_soft_refused`)
- **Heal** — `enforce_framing_ranking` tape-order restore of playable non-CTA primary impact; hard_keep restore; `cover_ranking_manifest_membership` orphans → excluded; envelope salvage / deterministic fallback without re-LLM
- **Wait_for_gate** — none (narrative_qc is config strict, not operator G*)
- **Done / hollow honesty** — `heal_or_refuse_mark`; lattice / sanitary debt pins ranking (sanitize verify-only after SOS S1)
- **Hard floors / QC bars** — never_exclude_primary_impact; hard_keeps in order; ordered∪excluded covers manifest; CTA never-touch off-air; story_health may warn-and-commit (fail path pins transitions/edl)
- **Freeze / never_touch / ownership** — producer of selection; CTA omit wins over must_keep; AuthorityDenied on foreign freezes (`content_brief`, `gap_evaluations`, narrative_plan) when soft paths touch them

### Considerations & load-bearing policy

- **Selection membership** starts here — every delivery consumer inherits ordered/excluded.
- Sanitize (post-S1) **verifies** lattice and refuses; **seal/restore is ranking’s job**.
- Primary impact comes from `gap_framing_plan` impact_blocks — upstream framing quality shapes who cannot be dropped.
- CTA / never-touch scraps are unenforceable as primary impact (skip restore) but still compete with framing debt when LLM/pack puts them in impact sets.
- Full-auto: no human ranking gate; NLE optional GUI overlay only.

### LLM / external calls

- Primary: `docs/prompts/selection/full-master-ranking.system.txt` via `run_flow_llm_stage` (≤2 attempts / stage invoke).
- Optional fail-open: STT lexicon specialist pre/post (no ranking `order_reconcile`).
- Hollow: empty / missing `ordered_segment_ids` → not persistable (salvage or refuse).

### What it deliberately does *not* do

- Does not write speakable gap VO (`gap_framing_compose`) or layup plan (only adopt binding)
- Does not shape-clean CTA/depth/family blowouts (`selection_order_sanitize`)
- Does not apply `covered_by_framing_vo` excludes (`selection_framing_apply`)
- Does not build EDL / synthesize WAV
- Does not write reorder bridges / SDP / gap VO rebudget (sanitize `ensure_ranking_side_artifacts`)

### Operator-visible effects

- NLE Save timeline → re-run ranking to merge `nle_edits.json`
- Failures surface as stage errors / soft-heal refuse / seed-order backlog for dependents
- No dedicated GUI gate; narrative_qc.strict can hard-stop before LLM

---

## 1. Job statement

Lock the air-order membership of the full master: every live segment is either on-air (ordered, lattice-legal) or explicitly excluded, so downstream delivery never invents who speaks.

---

## 2. Error-hint intake

From the high-risk report. Classify each predicate.

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `never_exclude_primary_impact` (pre-flush barrier) | `still_present_on_HEAD` (residual) + `healed` (partial) | Seal restores playable non-CTA; residual when impact is CTA/blank/unplayable or race after inject |
| Manifest segment missing from ordered ∪ excluded | `healed` (partial) | `cover_ranking_manifest_membership` stamps orphans into excluded |
| AuthorityDenied vs narrative_plan / manifest / gap_evaluations | `authority_friction` | Soft-freeze owners; ranking is not those owners |
| Seed-order “complete full_master_ranking before …” | `seed_order_noise` | Downstream backlog while ranking incomplete |
| `authority_undo_thrash` sanitize ↔ ranking | `authority_friction` | Shared selection SSOT; constitutional co-write, not unpaid land |

Report why-high-risk: never_exclude_primary_impact, freeze vs narrative/manifest

Classification values: `root_here` | `downstream_of_X` | `seed_order_noise` | `authority_friction` | `still_present_on_HEAD` | `healed`

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `stages/selection.py::run_full_master_ranking` |
| Persist / salvage | `persist_full_master_ranking`, `commit_persistable_ranking_from_last_envelope`, `commit_ranking_with_deterministic_fallback` |
| Finalize | `finalize_selection_order` (topo → hard_keep → CTA → integrity → story_health) |
| Lattice seal | `selection_constraints.seal_selection_lattice` → strip unplayable → `enforce_framing_ranking` → `enforce_hard_keeps` |
| Primary-impact | `framing_coverage_guard.validate_framing_ranking` / `enforce_framing_ranking` (`_merge_restored_in_tape_order`) |
| Manifest cover | `open_shape_repair.cover_ranking_manifest_membership` |
| Side artifacts (S6) | `ranking_side_artifacts.ensure_ranking_side_artifacts` from `selection_order_sanitize` |
| Commit bus | `air_order_boundary.commit_selection_mutation` |
| Contract | `docs/cross-cutting/stage-contracts/full_master_ranking.yaml` |
| Prompt | `docs/prompts/selection/full-master-ranking.system.txt` |
| Tests (non local-ML) | `test_fmr_hardening.py`, `test_f1_selection_lattice.py`, `test_framing_coverage_guard.py`, `test_ranking_persist_continue.py`, `test_hr4_ranking_sanitize_dirty_done.py`, `test_hr1_hitch_ranking_lattice.py` |

---

## 4. Business-logic walk

**Happy:** QC → LLM envelope with ordered ids → persist path: NLE/pack → one bind (seed XOR Shape) → hook/open_shape → inject lattice keeps → finalize → cover orphans → **single seal** → commit → heal mark. Sanitize later runs `ensure_ranking_side_artifacts`.

**Incomplete / refuse:** empty ordered; lattice critical after seal; integrity critical when blocked; pre-flush soft refuse on primary-impact residual.

**Heal:** framing restore by tape start; hard-keep restore; manifest orphans → excluded; envelope salvage without new LLM.

**LLM ≤2:** primary ranking only; specialists fail-open.

**Done honesty:** lattice / sanitary tokens pin `full_master_ranking`.

**HEAD structural (verified 2026-09-25 rescore):** no `_ranking_post_commit_sides` / no ranking `order_reconcile`; seal once immediately before `commit_selection_mutation` on LLM + salvage persist paths.

---

## 5a — Over-engineering scorecard (baseline, pre S1–S6)

| Check | Answer |
|-------|--------|
| Responsibilities count | **7+** |
| Dual / competing SSOTs | **yes** |
| Soft-heal / thrash re-admit loops | **yes** |
| Co-producer / unpaid land | **partial** |
| Brittle predicates vs simple rules | **partial** |
| Disproportionate shard/memo/resume | **partial** |
| “Fix everything downstream” behavior | **yes** |

**Over-engineered?** `yes`  
**Scorecard verdict:** **FAIL**

---

## 5b — Re-score after changes (S1–S6 on HEAD)

| Check | Answer | Fail-if? | Evidence |
|-------|--------|----------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **2** | no | (1) LLM + deterministic membership/bind path (2) lattice inject + CTA-safe finalize + single seal. Sides not counted (sanitize) |
| Dual / competing SSOTs | **partial** | no | Shared selection with sanitize is constitutional co-write — not fail-if `yes` |
| Soft-heal / thrash re-admit loops | **partial** | no | Bounded CTA/primary-impact restore inside seal; no mid+final dual seal; no post-seal side maze |
| Co-producer / unpaid land | **no** | no | Ranking is paid selection producer; bridges/SDP/rebudget on sanitize |
| Brittle predicates vs simple rules | **partial** | no | primary-impact vs never_touch/blank/hard-omit matrix remains product floor |
| Disproportionate shard/memo/resume | **no** | no | Envelope salvage only; no pick_best_order membership edit |
| “Fix everything downstream” behavior | **no** | no | No ranking order_reconcile; no post-commit sides in ranking |

**Fail-if hits:** 0  
**Over-engineered?** `no` — responsibilities ≤ 2; no fail-if `yes` rows  
**Scorecard verdict:** **PASS**

---

## 6. Complexity subtraction list

| id | P | Status / Change | Cleared |
|----|---|-----------------|---------|
| S1 | P0 | **done:** single seal before commit; mid-seal deleted | dual-seal theater |
| S2 | P0 | **done:** inject keeps before CTA; CTA restore for enforceable primary-impact | never_exclude thrash |
| S3 | P1 | **done:** one bind seed XOR Shape; rank_candidates metrics-only | pick_best_order membership edit |
| S4 | P1 | **done:** dropped ranking order_reconcile + layup adopt | post-seal membership mutate |
| S5 | P2 | **done:** contract soft trimmed | soft-input sprawl |
| S6 | P0 | **done:** deleted ranking post-commit sides; `ensure_ranking_side_artifacts` on sanitize | **responsibilities ≥3** |

**Open:** none (scorecard PASS).  
**Monitor:** never_touch/blank primary-impact residuals in forensics; shared-selection undo noise (constitutional).

---

## 7. Root-cause verdict

Baseline over-engineering was a membership maze (dual seal, mid-path restores, post-seal sides, order_reconcile). S1–S6 peel that to **propose/bind membership → seal once**. HEAD rescore confirms sides on sanitize and no ranking order_reconcile. Scorecard **PASS**. Residual primary-impact refuse cases are product floors, not stage bloat.

---

## 8. Recommended next action

`leave`

---

## 9. Scope fence

Upstream poison owner (if any): `gap_framing_compose` / `gap_framing_plan` impact_blocks; CTA labeling of impact tape; hitch remap lattice clear  
Downstream victims (names only): `selection_order_sanitize`, `nugget_layup_compose`, `air_script_compose`, `selection_framing_apply`, `transitions`, `edl_narrative_audit`, `edl`, `sound_design_plan`  
Did **not** redesign other stages.
