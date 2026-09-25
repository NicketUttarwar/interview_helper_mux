# High-risk stage audit — selection_order_sanitize

tier: T0 | seed: #41 | runs_hit: 8/9  
status: `complete`  
mode: investigate+shipped_subtractions  
updated: 2026-09-25T16:40:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path: read committed `master/selection.json` → run deterministic `sanitize_master_selection` (exact dedupe → drop never-touch CTA → collapse deep NLE fragments → same-family source-span collapse → same-family on-air cap → chapter clamp → ordered↔excluded reconcile → **lattice verify only** (refuse if primary-impact / hard-keeps missing — seal/restore is ranking’s job) → bump order lock + sanitize stamp) → write sanitize audit → `commit_selection_mutation(..., write_committed=True)` → `heal_or_raise` so seed-done is refused while sanitary errors remain.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `master/selection.json` | Produced by `full_master_ranking`; co-written here |
| Reads (soft) | `mastering/media_ip_cta.json`, `segments/manifest.json`, NLE/boundaries, `understanding/ideal_cuts.json`, reorder_bridges, talking_points | Starts map + never-touch + hard-keep inputs |
| Writes (SSOT) | `master/selection.json` | Shape-clean + lattice-seal co-producer via air-order bus |
| Soft / side | sanitize audit under operator / artifact_sanitize | Actions + metrics; not membership SSOT |

### Rules that govern it

- **Admit** — selection present + `result.ok` after sanitize (no residual shape/lattice criticals)
- **Refuse** — missing/invalid selection; `sanitize_refused:selection:` with errors (`segment_starts_unavailable`, hard-keep depth/span/family over budget, `chapters_emptied_by_sanitize`, critical lattice codes after restore)
- **Incomplete** — `heal_or_raise` / `selection_sanitary_errors` → pin sanitize or ranking (`selection still unsanitary`, `selection_needs_sanitize`, framing primary-impact)
- **Heal** — bounded drops only (never grow order); inherit letter-family spans into `_meta.inherited_segment_spans`; lattice debt pins ranking
- **Wait_for_gate** — none
- **Done / hollow honesty** — HR-4: refuse mark when sanitize not ok; consumers blocked while unsanitary (`selection_unsanitary` → resume here, or ranking for lattice tokens)
- **Hard floors / QC bars** — `max_fragment_depth` (default 3), `max_same_family_on_air` (default 8), never-touch CTA drop; never_exclude_primary_impact / hard-keep lattice criticals fail-closed (no restore here)
- **Freeze / never_touch / ownership** — writes via `commit_selection_mutation` + `write_committed_json`; paid-land aliases kept; order-unchanged commits preserve prior `producer_stage` (S4)

### Considerations & load-bearing policy

- **Selection membership** after ranking is this stage’s choke: every layup / SDP / EDL consumer asks `selection_sanitary_errors`.
- **Dual job on HEAD:** shrink air order (CTA/depth/family/span) **and** grow it again via `apply_selection_constraints` → `enforce_framing_ranking` tape-order restore. That restore exists because ranking can leave primary-impact excluded; sanitize became the safety net (exec_13198 sticky incomplete).
- **Publishability:** never-touch CTA must stay off-air (`max_cta_readmit: 0`); primary-impact restore must skip unplayable/CTA tape.
- **Full-auto:** no human gate; refuse loops if upstream lattice/NLE starts broken — honest stall, not silent hollow done.

### LLM / external calls

N/A — deterministic process stage. Contract YAML still lists `llm_execute` in lifecycle phases (doc drift vs body).

### What it deliberately does *not* do

- Does not invent ranking scores or narrative chapter titles (ranking / narrative_arc_plan)
- Does not write gap_report / layup / EDL / mix
- Does not repair air-order *integrity* jumps (metrics-only; ranking owns repair)
- Does not own media_ip_cta production (ranking writes; sanitize only consumes never-touch set)

### Operator-visible effects

- Sanitize refuse surfaces as stage error / incompleteness pin (resume sanitize or ranking)
- Order mutations invalidate downstream via air-order lifecycle bus
- No GUI gate; Full-auto stalls on refuse until upstream or NLE starts heal

---

## 1. Job statement

Deterministically clean and lattice-seal the locked air order in `master/selection.json` so downstream delivery never builds on unsanitary membership (duplicates, CTA scraps, fragment/family blowouts, missing primary-impact / hard-keeps).

---

## 2. Error-hint intake

From the high-risk report. Classify each predicate.

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `master/selection.json has newer uncommitted pending` | `authority_friction` | HC-3 in `write_staging`; foreign pending races with sanitize commit / co-writers — not a membership-rule bug |
| `framing:primary impact … never_exclude_primary_impact` | `healed` (partial) + `downstream_of_X` (`full_master_ranking`) | Step 7c + tape-order merge restore on HEAD (`test_sanitize_restores_primary_impact_not_selected`); residual when impact is unplayable/CTA or starts missing |
| `authority_undo_thrash` / hash or action oscillation | `authority_friction` | sanitize ↔ ranking / `edl_narrative_metadata_align` on shared selection; aliases paid in `done_authority` but undo ledger still noisy |
| `sanitize_refused: segment_starts_unavailable` | `still_present_on_HEAD` | Honest refuse when multi-member families lack starts; inherit/pending-NLE/hints mitigate — still refuse when unresolved |
| Restores media_ip_cta / never_touch primaries | `healed` (partial) | Drop path + `_impact_source_is_unenforceable` skip CTA/blank restore; thrash if ranking re-admits scraps |

Report why-high-risk: Uncommitted pending, primary-impact restore, authority_undo oscillation

Classification values: `root_here` | `downstream_of_X` | `seed_order_noise` | `authority_friction` | `still_present_on_HEAD` | `healed`

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `artifact_sanitize/selection.py::run_selection_order_sanitize` |
| Core sanitize | `sanitize_master_selection` (same file) — steps 1–8 |
| Lattice restore | `selection_constraints.apply_selection_constraints` → `framing_coverage_guard.enforce_framing_ranking` (`_merge_restored_in_tape_order`) + `hard_keep.enforce_hard_keeps` |
| Sanitary gate | `selection_sanitary_errors` / `_shape_sanitary_errs` / `_lattice_and_integrity_errs` |
| Commit bus | `air_order_boundary.commit_selection_mutation` (`write_committed=True`) |
| Done honesty | `stage_completion` (selection_order_sanitize branch) + `heal_or_raise` |
| Freeze / ownership | `artifact_ownership` ALLOW on `master/selection.json`; `done_authority._SHARED_PATH_LAND_CO_PRODUCERS` aliases |
| Config | `artifact_sanitize.config.sanitize_selection_cfg` |
| Contract | `docs/cross-cutting/stage-contracts/selection_order_sanitize.yaml` |
| Tests (non local-ML) | `test_artifact_sanitize_selection.py`, `test_sos_harden.py`, `test_hr4_ranking_sanitize_dirty_done.py`, `test_sanitize_authority_thrash.py`, `test_i13183_selection_residues.py` |

---

## 4. Business-logic walk

**Happy:** selection on disk → sanitize passes (`ok`, shape drops + lock bump; lattice verify clean) → audit written → committed via air-order bus → heal sees empty sanitary errors → mark done.

**Incomplete / refuse:** `result.ok` false → `RuntimeError("sanitize_refused:selection: …")` — no commit. Lattice criticals (primary-impact / hard-keep) pin ranking. Heal also refuses when dry sanitize would still mutate (`selection_needs_sanitize:…`).

**Heal (bounded):**
1. Shape drops (dedupe, never-touch, depth, span, family) into excludes with honest reasons — never grow order.
2. Persist `_meta.inherited_segment_spans` so letter kids do not re-trip starts.
3. Lattice verify only — missing primary-impact/hard-keeps → refuse (seal at ranking).
4. Stale stamp + cosmetic-only dry run → sanitary for consumers **without** disk write (S2).

**LLM ≤2:** N/A.

**Done honesty:** HR-4 tests assert refuse does not mark; sanitary run marks. Consumers pin sanitize for shape tokens; lattice tokens pin ranking.

**Integrity criticals:** metrics only inside sanitize — ranking owns jump repair.

---

## 5. Over-engineering scorecard

*Re-scored 2026-09-25 after S1–S4 shipped.*

| Check | Before | After (HEAD) | Evidence |
|-------|--------|--------------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **4+** | **2** | Shape-clean (+ chapter/exclude/starts as support) · lattice **verify** only — restore peeled |
| Dual / competing SSOTs | **yes** | **partial** | Shared file remains (ranking seal + narrative meta); sanitize no longer grows membership |
| Soft-heal / thrash re-admit loops | **yes** | **no** | No `apply_selection_constraints` grow-back; no off-bus restamp; order-unchanged skips undo ledger |
| Co-producer / unpaid land | **yes** | **partial** | Paid aliases kept by design; S4 preserves producer on meta-only so ownership does not flip |
| Brittle predicates vs simple rules | **partial** | **partial** | Starts-unavailable + inherit/pending NLE still dense but needed for letter families |
| Disproportionate shard/memo/resume | **no** | **no** | Still single-pass |
| “Fix everything downstream” behavior | **partial** | **no** | Ranking seal owns primary-impact debt; sanitize refuses |

**Over-engineered?** `no` — flagged thrash/restore/safety-net behaviors cleared; residual shared-SSOT + starts-map density are constitutional, not stage bloat.

**Scorecard result:** **PASS**

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Change | Acceptance hint | Status |
|----|---|------------------------|--------|-----------------|--------|
| S1 | P0 | unambiguous | Peel step 7c lattice restore out of sanitize; verify-only refuse; seal at ranking | Sanitize never grows order; primary-impact → refuse + pin ranking | **shipped** 2026-09-25 |
| S2 | P1 | unambiguous | Stop off-bus `_restamp_selection_sanitize_meta` from `selection_sanitary_errors` | Probe returns [] when cosmetic-ok; no disk write | **shipped** 2026-09-25 |
| S3 | P1 | unambiguous | Contract: drop `llm_execute`; document co-writers | YAML process-only | **shipped** 2026-09-25 |
| S4 | P2 | resolved | Keep paid-land aliases; on order-unchanged commit preserve prior `producer_stage` + skip undo ledger | Meta-align does not flip owner vs sanitize | **shipped** 2026-09-25 |

---

## 7. Root-cause verdict

High-risk was **dual ownership of air-order membership**: this stage both culled and re-admitted while sharing the SSOT with ranking/narrative. S1–S4 shipped: sanitize is now **shape-only + lattice verify/refuse**; seal/restore stays on `full_master_ranking`; sanitary probe no longer writes; meta-only commits preserve producer and stay off the undo ledger.

---

## 8. Recommended next action

`leave` (subtractions shipped; further work only if ranking seal gaps reappear in forensics)

---

## 9. Scope fence

Upstream poison owner (if any): `full_master_ranking` (primary-impact excludes / lattice seal debt); NLE/boundaries for starts  
Downstream victims (names only): `nugget_layup_compose`, `sound_design_plan`, `selection_framing_apply`, `edl_narrative_audit`, `edl`, `transitions`, `mix`  
Did **not** redesign other stages.
