# High-risk stage audit — mix

tier: T2 | seed: #64 | runs_hit: 8/9  
status: `not_started`  
mode: investigate  
updated: 2026-09-25T15:54:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

(Happy-path narrative: inputs → decisions → outputs.)

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads | | |
| Writes (SSOT) | | |
| Soft / side | | |

### Rules that govern it

- Admit /
- Refuse /
- Incomplete /
- Heal /
- Wait_for_gate /
- Done / hollow honesty /
- Hard floors / QC bars /
- Freeze / never_touch / ownership /

### Considerations & load-bearing policy

(G-Framing, G1, hosted VO, selection membership, publishability, Full-auto defaults — what this stage owns vs depends on.)

### LLM / external calls

Prompt ids / ≤2 attempts / hollow meaning — or N/A.

### What it deliberately does *not* do

(Boundaries vs upstream / downstream.)

### Operator-visible effects

(Gates, GUI, Full-auto-only behaviors.)

---

## 1. Job statement

One sentence product purpose (code + contract, not marketing).

---

## 2. Error-hint intake

From the high-risk report. Classify each predicate.

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `incomplete_cut_unresolved` | | |
| `mix_seat` | | |

Report why-high-risk: incomplete_cut_unresolved, mix_seat, delight freeze

Classification values: `root_here` | `downstream_of_X` | `seed_order_noise` | `authority_friction` | `still_present_on_HEAD` | `healed`

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | |
| Key helpers | |
| Primary writes | |
| Freeze / ownership | |
| Tests (non local-ML) | |

---

## 4. Business-logic walk

Detail beyond §0: happy / incomplete / refuse / heal / LLM ≤2 / done honesty. Cite code pointers.

---

## 5. Over-engineering scorecard

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | | |
| Dual / competing SSOTs | | |
| Soft-heal / thrash re-admit loops | | |
| Co-producer / unpaid land | | |
| Brittle predicates vs simple rules | | |
| Disproportionate shard/memo/resume | | |
| “Fix everything downstream” behavior | | |

**Over-engineered?** _(fill)_ `yes` | `partial` | `no` — one-line why.

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Change | Acceptance hint |
|----|---|------------------------|--------|-----------------|
| S1 | P0 | | | |

---

## 7. Root-cause verdict

_(fill after investigation)_

---

## 8. Recommended next action

_(pick one)_ simplify | split_stage | move_policy_upstream | delete_path | leave | fix_now

---

## 9. Scope fence

Upstream poison owner (if any):  
Downstream victims (names only):  
Did **not** redesign other stages.
