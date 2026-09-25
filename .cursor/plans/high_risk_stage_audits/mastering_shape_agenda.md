# High-risk stage audit — mastering_shape_agenda

tier: T3 | seed: #27 | runs_hit: 9/9  
status: `complete`  
mode: investigate  
updated: 2026-09-25T18:20:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path (Full-auto defaults: `soft_gate.enable=true`, `shape.llm.enabled=true`): after research rollup is seed-complete → compile a provisional evidence packet → invoke meta-architect prompt (≤2) for `mastering/shape/agenda.json` → lint/schema-coerce → invoke eval-rubric mint (≤2) → write `mastering/shape/eval_rubric.json` → `heal_or_refuse_mark(..., force=True)`.

If `shape.llm` is off: write heuristic agenda + advisory rubric (mode priors from style hints) and heal. If soft_gate disabled: schema-valid skip stub and heal.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard, contract) | `mastering/research/rollup.json` | Producer `mastering_research_rollup`; admit also gated by A-01 shape-core thin rails |
| Reads (soft) | dossier, content_brief, topology, talking_points, ideal_cuts, gaps, selection, manifest, plan, candidates | Often thin/absent at Pass1 (before missing_framing) |
| Writes (SSOT) | `mastering/shape/agenda.json` | Sole product owner |
| Writes (ops) | `mastering/shape/eval_rubric.json` | Same stage, `mode=operational` |
| Soft / side | `mastering/evidence_packets/shape_agenda_pass1.json` | Via `compile_shape_evidence` → `ops` ownership |

### Rules that govern it

- **Admit** — Seed order after `mastering_research_rollup` (routing → waves → rollup → this); soft_gate on
- **Refuse / incomplete** — CSP-05: hollow/invalid agenda or rubric after ≤2 LLM attempts → `StageError` / incompleteness (no soft-heal done). A-01: research shape-core thin → resume rollup
- **Incomplete** — HM-1 schema hollow on agenda; `shape_agenda_rubric_llm_failed_incompleteness` when rubric/agenda stamped `llm_failed`
- **Heal** — Force mark_done only after contentful agenda+rubric (or honest soft_gate skip stub)
- **Wait_for_gate** — N/A
- **Done / hollow honesty** — LLM-on path never heals hollow; heuristic-off path may land degraded stub on exception
- **Hard floors / QC bars** — Schema steps/budgets/north_star_pillars; soft_gate never authoritative (`consumers_bind` default false)
- **Freeze / never_touch / ownership** — Owns agenda (+ operational rubric); does not mutate selection / gap_report / plan

### Considerations & load-bearing policy

- **Advisory L0** — Shape soft-gate does not bind consumers under defaults; listen_delight / later plan stages remain ship authority
- **Full-auto** — `shape.llm.enabled=true` by default → OpenAI required for honest done; stalls are intentional honesty, not soft stub
- **Upstream** — Looks hot in ledgers when research_routing / rollup / thin-dossier seed-order races (T3 class)
- **Publishability** — Indirect only; wrong mode hypothesis can bias candidates/plan while `consumers_bind` stays false

### LLM / external calls

- Prompt ids: `mastering/shape-meta-architect.system.txt`, `mastering/eval-rubric-mint.system.txt` (registry OH-S0)
- ≤2 attempts each via `invoke_mastering_prompt`
- Hollow meaning: no mode signal / schema-invalid agenda; rubric without criteria|style_axes

### What it deliberately does *not* do

- Does not mint candidates or synthesize `mastering_plan` (downstream stages in same module)
- Does not probe research fields / write routing or rollup
- Does not own selection membership, gaps, or authoritative delight

### Operator-visible effects

- No dedicated GUI gate; Phase workbench lists under analysis Shape
- Full-auto: hollow OpenAI → driver incomplete / identical-failure halt (CSP-05)
- Soft_gate off → skip stub, stage still seed-complete

---

## 1. Job statement

Mint the Pass-1 Shape soft-gate **agenda** (and paired **eval rubric**) from research evidence — LLM when configured, else heuristic — without soft-claiming done on hollow OpenAI output.

---

## 2. Error-hint intake

From the high-risk report. Classify each predicate.

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| Seed-order vs `research_routing` / rollup | `seed_order_noise` | Analysis order pins routing→waves→rollup before agenda; ledger noise when upstream incomplete |
| Hollow / invalid OpenAI agenda or rubric | `still_present_on_HEAD` (by design) | CSP-05 refuse incomplete; not soft-heal. Default `shape.llm` on makes this the Full-auto failure mode |
| Research shape-core thin / dossier stale (A-01) | `downstream_of_mastering_research_rollup` | Consumer pin until rollup refreshes; not agenda body bloat |
| Schema / HM-1 hollow agenda | `healed` / rails | `ensure_schema_agenda` + validator; skip stub still schema-valid |

Report why-high-risk: Research routing prereq + hollow OpenAI agenda

Classification values: `root_here` | `downstream_of_X` | `seed_order_noise` | `authority_friction` | `still_present_on_HEAD` | `healed`

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `mastering_shape_runtime.py::run_mastering_shape_agenda` (pipeline dispatch) |
| Key helpers | `_heuristic_agenda_and_rubric`, `_agenda_from_llm` / `_lint_shape_agenda_llm`, `_rubric_from_llm`, `ensure_schema_agenda`, `_shape_llm_user_payload`, `compile_shape_evidence` |
| Primary writes | `mastering/shape/agenda.json`, `mastering/shape/eval_rubric.json` |
| Freeze / ownership | `artifact_ownership.py` agenda ALLOW; rubric operational; evidence packets `ops` |
| Honesty rails | `openai_primary_honesty.shape_agenda_rubric_llm_failed_incompleteness`; `stage_completion` MSA + A-01 thin refuse |
| Tests (non local-ML) | `tests/test_a03_mastering_llm_cutover.py`, `tests/test_hm1_schema_hollow.py`, `tests/test_csp05_openai_primary_honesty.py`, `tests/test_research_thin_latch.py`, `tests/test_category_b_ws1_shape.py` |

---

## 4. Business-logic walk

1. **soft_gate off** → `_persist_shape_agenda_skip` + heal → return.
2. **shape.llm on** → evidence payload → meta-architect ≤2 → lint agenda (normalize prompt `levels`, map `custom_steps`→`steps`) → if None: `raise_hollow_openai_primary(...agenda_llm_hollow)`. Rubric mint ≤2 → if None: write agenda + stub rubric (`llm_failed`, notes) → raise hollow. Else write both → heal.
3. **shape.llm off** → `_heuristic_agenda_and_rubric` (priors + soft_gate max candidates) → write → heal.
4. **Exception** → if LLM on: re-raise as hollow incompleteness; if LLM off: degraded stub agenda+rubric → heal (fail-open heuristic).
5. **Done honesty** — incompleteness also re-checks stamped `llm_failed` / `rubric_llm_failed` so orphan promote cannot restamp done over hollow LLM land.
6. **Admit friction outside body** — `_research_thin_late_refuse` for `RESEARCH_CONSUMER_STAGES` including this id.

Cite: `mastering_shape_runtime.py` ~734–840; `openai_primary_honesty.py` ~58–74; `stage_completion.py` ~1559–1581, ~893–937.

---

## 5. Over-engineering scorecard

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **2** | (1) mint agenda SSOT; (2) mint paired eval rubric. Evidence packets are shared `ops` compile, not a third product job |
| Dual / competing SSOTs | **no** | Sole agenda writer; soft_gate advisory (`consumers_bind` false); plan/candidates owned downstream |
| Soft-heal / thrash re-admit loops | **no** | CSP-05 hard incomplete on hollow LLM; no heuristic fall-through when `shape.llm` on |
| Co-producer / unpaid land | **no** | Pays own agenda+rubric; does not thrash-land selection/gap_report |
| Brittle predicates vs simple rules | **no** | Schema/signal lint + typed hollow refuse; thin latch is rollup policy, not agenda kitchen-sink |
| Disproportionate shard/memo/resume | **no** | No shard/memo; two prompt invokes are the product path, not resume thrash |
| “Fix everything downstream” behavior | **no** | Does not rewrite membership / gaps / plan; advisory L0 only |

**Over-engineered?** `no` — two paired Pass-1 outputs, honest LLM refuse, no dual SSOT or unpaid co-produce.

**Scorecard verdict:** `PASS`

- `PASS` only if Over-engineered? = `no`
- One line: N/A (already PASS). Residual T3 ledger heat is seed-order / rollup thin, not stage bloat.

### 5b — Re-score after changes (MODE=fix / MODE=rescore only)

_(not applicable — investigate only)_

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| — | — | — | — | Scorecard PASS — no open cuts. Optional monitor: dual LLM cost while `consumers_bind=false` (product policy, not peel). | — | leave |

Status: no open rows · Operator decisions: none required.

---

## 7. Root-cause verdict

Report heat is **not** over-engineering of this stage. Typical 9/9 hits are (a) **seed-order / A-01 thin** waiting on research routing→rollup, and (b) **CSP-05 hollow OpenAI** when `shape.llm` is on — both recovered or halted honestly. Body is a single Pass-1 mint with clear skip / heuristic / LLM branches.

---

## 8. Recommended next action

`leave`

---

## 9. Scope fence

Upstream poison owner (if any): `mastering_research_rollup` (thin/stale dossier); occasionally `mastering_research_routing` seed-order race  
Downstream victims (names only): `mastering_shape_candidates`, `mastering_plan_synthesize`  
Did **not** redesign other stages.
