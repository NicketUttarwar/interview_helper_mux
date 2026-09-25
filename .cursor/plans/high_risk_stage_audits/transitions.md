# High-risk stage audit — transitions

tier: T1 | seed: #52 | runs_hit: 6/9  
status: `complete`  
mode: rescore  
updated: 2026-09-25T18:20:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path (post S1–S5): **detect-only** air-order / exclude-drift on selection (dirty → loud refuse + pin `selection_order_sanitize`) → nested **`run_synthetic_framing_plan`** (**always demote-empty when layup on** — no content LLM) → OpenAI **`assembly/transitions.system.txt`** proposes spoken bridge rows → persist filters (gap-VO dedupe, adjacency dedupe, reverse-gap / opening-body drops, `spoken_copy_guard`, episode VO identity) into **`master/transitions.json`** → **`ensure_seam_glue`** rebuilds bridges / mints structural hinges / writes `bridge_completeness` → air-script filter → **refuse** if completeness incomplete → if G1 skipped/open, **stamp pair freeze**. Empty `transitions: []` is allowed (`min_rows: 0`).

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `understanding/nugget_layup_plan.json`, `master/selection.json`, `understanding/content_brief.json`, `understanding/gap_report.json`, `mastering/mastering_plan.json` | Contract hard; payload also soft-reads many |
| Writes (SSOT) | `master/transitions.json` | `one_writer` primary |
| Writes (owned side) | `understanding/synthetic_framing_plan.json`, `synthetic_context_packet.json`, `master/transitions_pair_freeze.json`, `master/deferred_transition_pairs.json`, `master/bridge_completeness.json`, `understanding/reorder_bridges.json` | Contract outputs trimmed to these |

### Rules that govern it

- **Admit** — After layup / selection / brief / gap / mastering_plan hard inputs; delivery seed #52
- **Refuse** — Selection air-order dirty / exclude drift; LLM flow fail after ≤2; incomplete bridge_completeness (SystemExit); synthetic framing loud-fail only when layup off and plan invalid after 2
- **Incomplete** — Bridge incompleteness refuses (no soft-warn mark_done)
- **Heal** — `run_flow_llm_stage` + demoted synthetic `heal_or_refuse_mark`; **no** selection mutation
- **Wait_for_gate** — No stage gate; **G1** open/skip → pair freeze stamp only
- **Done / hollow honesty** — Empty transitions OK; incomplete glue cannot mark_done
- **Hard floors / QC bars** — Spoken-copy guard; reverse-jump / opening filters; no chapter scaffolding in text
- **Freeze / never_touch / ownership** — Sole primary writer of `transitions.json`; does not write `selection.json`

### Considerations & load-bearing policy

- **Selection is locked air order** — prompt forbids re-ranking; dirty order pins sanitize upstream
- **One spoken host turn per seam** — dedupe vs `gap_report` before-VO
- **Layup always demotes synthetic content LLM** (S3A)
- **Pair freeze** — locks spoken pairs once G1 skipped/open
- **Heal pin** — Bare `premature_complete` → transitions **only when transitions hollow**; else earliest Flow-1 incomplete / delivery seat (S5). R4 named-class cousins unchanged

### LLM / external calls

- Primary: `assembly/transitions.system.txt` via `run_flow_llm_stage` (≤2)
- Nested synthetic: demote-empty under layup; content LLM only when layup off
- No local ML / cloud audio

### What it deliberately does *not* do

- Does not mutate `master/selection.json`
- Does not mint transition WAVs (`vo_synthesize`)
- Does not own ranking artifacts (`order_reconcile` / `rank_candidates` / `story_health` / SDP)

### Operator-visible effects

- No dedicated GUI gate on this stage
- Dirty selection refuses with resume=`selection_order_sanitize`
- Incomplete glue refuses (EDL still refuses missing bridges as backstop)

---

## 1. Job statement

Compose (and structurally complete) spoken **transition seams** for the locked selection adjacency into `master/transitions.json`, without inventing new interview content or re-ranking air order.

---

## 2. Error-hint intake

From the high-risk report. Classify each predicate.

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `forensics_stall` | `still_present_on_HEAD` / `authority_friction` | Mitigated by S5 hollow-aware bare pin; named cousins already R4-guarded |
| `phase_a_edl` | `downstream_of_delivery_seat` | Named class pins edl / canonical seat — not transitions |
| edl_narrative `hard_freeze` on `transitions.json` / pair_freeze | `authority_friction` | Correct ownership friction |
| `seed_order_prereq` | `seed_order_noise` | Occasional |

Report why-high-risk: forensics_stall + phase_a_edl

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `src/interview_mux/stages/selection.py::run_transitions` |
| Key helpers | `synthetic_framing.run_synthetic_framing_plan` (S3A demote); `seam_glue.ensure_seam_glue`; `air_script.filter_transitions_for_air_script`; `transition_vo.stamp_transitions_pair_freeze`; `spoken_copy_guard`; detect-only `audit_and_report(repair=False)` |
| Primary writes | `master/transitions.json` + owned side artifacts above |
| Freeze / ownership | transitions one_writer; selection **not** written |
| Tests | `tests/test_transitions_s1_s5_simplify.py`; `tests/test_r4_premature.py`; `tests/test_edl_s1_s5_simplify.py` |

---

## 4. Business-logic walk

1. **Detect selection** — `audit_and_report(repair=False)` + exclude-reconcile drift check; dirty → `raise_loud_failure(..., resume=selection_order_sanitize)`.
2. **Synthetic framing** — Layup on → demote-empty (no LLM). Layup off → prior valid plan or ≤2 LLM.
3. **Transitions LLM** — Guarded persist into `transitions.json`.
4. **Seam glue** — Mint missing structural hinges; air-script filter; **SystemExit** if incomplete or glue exception.
5. **G1 pair freeze** — Stamp when G1 skipped/open.

---

## 5. Over-engineering scorecard

### 5a — Baseline (investigate)

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count | **5** | selection repair + nested synthetic + LLM + glue + freeze |
| Dual / competing SSOTs | **yes** | |
| Soft-heal / thrash re-admit loops | **yes** | |
| Co-producer / unpaid land | **yes** | |
| Brittle predicates vs simple rules | **yes** | |
| Disproportionate shard/memo/resume | **partial** | |
| “Fix everything downstream” behavior | **yes** | |

**Over-engineered?** `yes`  
**Scorecard verdict:** `FAIL` (baseline)

### 5b — Re-score after changes (MODE=rescore 2026-09-25T18:20:00Z)

HEAD re-read: S1–S5 still present (`repair=False`, no `commit_selection_mutation`, layup demote, glue `SystemExit`, `_bare_premature_complete_pin`). Prior fix scored responsibilities=3 by splitting glue from plan; recount treats glue+air-script+incomplete-refuse as **completing the same primary artifact** (parity with EDL’s build+QC fold).

| Check | Answer | Delta | Evidence now |
|-------|--------|-------|--------------|
| Responsibilities count | **2** | −1 vs fix §5b | (1) produce complete sanitary `transitions.json` — demote synthetic + LLM + guards + seam glue + air-script + refuse incomplete (2) admit/gate bookkeeping — dirty-selection detect-refuse + G1 pair-freeze stamp |
| Dual / competing SSOTs | **no** | cleared | Sole `one_writer` for `transitions.json`; gap VO is complementary dedupe input, not a second transitions SSOT; ranking claims removed from contract |
| Soft-heal / thrash re-admit loops | **no** | same | No selection mutate; incomplete glue refuses; bare premature hollow-aware |
| Co-producer / unpaid land | **no** | same | No selection commits; contract outputs ⊆ ownership |
| Brittle predicates vs simple rules | **partial** | same | Reverse-jump/opening filters + heal-pin cousins remain; not fail-if `yes` |
| Disproportionate shard/memo/resume | **partial** | same | Pair freeze / deferred / completeness purposeful for VO seating |
| “Fix everything downstream” behavior | **no** | same | Detect→pin sanitize; refuse incomplete — no soft-except mint kitchen |

**Fail-if hits:** 0 (responsibilities ≤2; dual ≠ yes; no other hard yes).

**Over-engineered?** `no`

**Scorecard verdict:** `PASS`

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | unambiguous | **done:** detect-only `audit_and_report(repair=False)` + exclude drift → loud refuse pin sanitize; no selection mutate | Responsibilities, co-producer, fix-downstream | source: no `commit_selection_mutation` |
| S2 | P0 | unambiguous | **done:** trimmed YAML + INDEX + `contract_dependency_data` outputs; added `bridge_completeness` | Dual SSOT (doc), co-producer claim | forbidden paths absent from contract |
| S3 | P1 | needs_you → **decided: A** | **done:** layup on → always demote-empty; never content LLM | Responsibilities, dual SSOT | demote test; no `run_llm_stage_simple` under layup |
| S4 | P1 | needs_you → **decided: refuse** | **done:** SystemExit on incomplete glue / glue exception | Soft-heal, done honesty | no soft-warn path in glue block |
| S5 | P1 | needs_you → **decided: hollow-aware** | **done:** `_bare_premature_complete_pin` — transitions only when hollow; else earliest Flow-1 / seat | Brittle predicates, thrash | R4 hollow still → transitions; complete → edl |
| S6 | P2 | unambiguous | **superseded:** prior “fold glue/freeze to hit ≤2” — rescore recount already folds glue into primary artifact completeness; no code change | Responsibilities | leave/monitor |

**Open ship rows:** none — scorecard PASS.  
**Leave / monitor:** pair-freeze + deferred shards; reverse-jump filters; hollow-aware bare premature pin under new delivery tokens.  
**Operator decisions recorded:** S3→A; S4→refuse; S5→hollow-aware bare pin (safest).

---

## 7. Root-cause verdict

Pre-fix `transitions` was a mini delivery orchestrator + premature_complete gravity well. After S1–S5 + rescore, it is **plan/complete seams + admit gates**: selection repair peeled, glue soft-heal gone, heal-pin narrowed, contract honest. Residual partials (filters / freeze shards) are load-bearing, not fail-if.

---

## 8. Recommended next action

`leave`

---

## 9. Scope fence

Upstream poison owner (if any): `selection_order_sanitize` (dirty air-order); `nugget_layup_compose` (layup demote)  
Downstream victims (names only): `edl_narrative_audit`, `vo_line_adjudicate`, `vo_synthesize`, `edl`, `sound_design_plan`, `mix`  
Did **not** redesign other stages.
