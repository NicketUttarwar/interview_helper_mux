# Deferred optional revisit questions (next net)

Append-only. Items parked from an optional KEEP batch for a later ask — with full forms.

## Parked 2026-09-18 — MPS `consumers_bind` (Q7 skip)

### Full forms (this family)

| Abbr | Full name | What it is |
|------|-----------|------------|
| **MPS** | **Mastering Plan Synthesize** (`mastering_plan_synthesize`) | Writes `mastering/mastering_plan.json` from Shape candidates / soft-gate. |
| **MSC** | Mastering Shape Candidates (`mastering_shape_candidates`) | Competes narrative-mode candidates. |
| **MSA** | Mastering Shape Agenda (`mastering_shape_agenda`) | L0 agenda + eval rubric for Shape. |
| **MPC** | Mastering Plan Confirm (`mastering_plan_confirm`) | Pass-2 confirm of provisional plan. |
| **CSP-05** | Cross-Stage Pattern 05 | Hollow OpenAI must not heal done — incompleteness after ≤2. |
| **A-03** | Mastering LLM cutover | Shape/research LLM flags; soft_gate never authoritative complete. |

### What `consumers_bind` means

- Config: `mastering.shape.soft_gate.consumers_bind` (default **`false`**).
- When **false** (today): Shape soft-gate / plan may finish without requiring every downstream “consumer” of the plan (bind/order/selection clients) to have already bound to a complete plan. Unattended Full-auto progresses on a **degraded / advisory** plan until Shape LLM (when on) can claim complete.
- When **true**: plan path waits on consumer bind — stricter honesty that nothing downstream is acting on an unbound plan, but **higher Full-auto stall / thrash risk** if consumers are not ready (FARR).

### Why it was deferred

Operator asked to skip for now and re-ask later with more context (this note). Q6B already flipped `shape.llm.enabled=true` with packed payloads + response lint; leave `consumers_bind=false` until live runs show unbound-plan poison.

### Suggested next-ask wording

**Q — MPS `consumers_bind`**
Today: soft-gate does **not** wait on consumers (`consumers_bind=false`).
- **A)** KEEP false (finishability; plan may be unbound advisory)
- **B)** Flip true (stricter bind; Full-auto regression risk)

Recommend after watching a Full-auto Shape→selection→air path under Q6B LLM-on.

### Resolved 2026-09-18 — operator answer

**A) KEEP false.** Intentional: hybrid bind already prefers Shape order only when `plan_status=complete` + healthy; degraded stays advisory so ranking/selection/air decide. Flip true only if live runs show unbound-plan poison (not observed as a clinic blocker). Next-ask net empty.
