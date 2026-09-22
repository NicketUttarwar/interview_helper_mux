# DP-B5 — ESR clears wait on bare is_done (hollow escape)

- status: awaiting_operator
- created: 2026-09-21T17:15:00Z
- blocks: HOLLOW_DONE + ESR_POST_MASTER; ship wait lies
- resume_hook: /partial-zero-answer DP=B5 VERDICT=…
- solution_swarm_agents: packet merge (mechanism honesty + HEAD verify); no product patches this turn

## TL;DR (read this first)
- What’s wrong: `should_wait_incomplete_after_conductor` still clears wait on bare `is_done(pin)` (and exception→any `is_done`), including ship-pin paths — hollow markers can stop ESR wait without seed-complete.
- What you’d notice: Ship walk “done waiting” while outputs missing; or opposite thrash if over-strict.
- Why Partial: Hollow done must not clear ship wait.
- Agent recommendation: Option **A** — only `seed_stage_complete(pin)` (+ committed master rules for post-family) may clear wait; delete bare `is_done` escapes (stricter than mechanism Decision B5-3).
- What that gives up: Aggressive “don’t stall ship” on marker-only finalize.

## Context (enough to decide)
- Where: `execution_status.should_wait_incomplete_after_conductor`.
- Cousin family: **HOLLOW_DONE** / **ESR_POST_MASTER** / **SHIP_BAR_VOCAB**.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Seed-complete only clears wait (delete is_done escapes) | Hollow-proof Partial | More waits until outputs real |
| B | Keep ship-pin is_done; delete exception any-pin escape | Minimum harden | Ship hollow still clears |
| C | Keep both escapes (mechanism B5-3 / HEAD-ish) | Max don’t-stall-ship | Hollow wait-clear |
| Defer | | Wait | Delay |

## Option A — Seed-complete only (recommended for Partial)
**What we would do:** Remove `or ctx.is_done(pin_s)` early exits and exception `is_done` escapes; rely on seed_complete + C1 post-family + `pipeline_complete`.
**Pros:** Hollow markers cannot end wait.
**Cons:** More waits until real outputs.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes hollow ESR cousin |
| Complexity left | Must trust seed_complete |
| What you give up | Marker-only ship advance |
| Human work | Audit ship waits |
| Implement cost | Medium |
| Regression risk | Medium (more waits) |
| Reversibility | High |

## Option B — Keep ship-pin is_done; drop exception escape
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium |
| Cousin closure | Partial |
| Complexity left | Medium |
| What you give up | Full hollow-proof |
| Human work | Less |
| Implement cost | Low-medium |
| Regression risk | Low-medium |
| Reversibility | High |

## Option C — Keep both (current bias)
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low-medium |
| Cousin closure | Leaves hollow escape |
| Complexity left | Low |
| What you give up | Wait honesty |
| Human work | None |
| Implement cost | Zero |
| Regression risk | High hollow |
| Reversibility | N/A |

## Option Defer
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | None |
| Complexity left | Unchanged |
| What you give up | Policy |
| Human work | Watch |
| Implement cost | Zero |
| Regression risk | Zero |
| Reversibility | N/A |

## Recommendation (not a decision)
- Preferred: Option **A**
- Why Partial: Bare `.stage_done` must not end ESR wait — HOLLOW_DONE root feeding ship lies. Mechanism Decision B5-3 optimized “don’t stall”; campaign law prefers honesty.
- Honest downside: Hollow finalize waits longer until seed-complete or C1/C2 paths fire.
- Devil’s-advocate: B is the minimum viable harden if A causes ship stalls in practice.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | Hollow marker + master.wav → no wait |
| Thrash tax | Later publish defects / identical |
| Cousin surface area | ESR + driver + agenda |
| Benefit under Partial | Wait truth |
| Replaceability | CUT is_done wait-clear |

## Evidence appendix
- HEAD: `execution_status.py` should_wait — still has `seed_stage_complete or is_done` and exception `is_done` escapes (~690–727)
- Hints: mechanism BP-B5 Decision B5-3; cousin HOLLOW_DONE

## Your verdict
- choice: A | B | C | Defer | custom: …
- notes:
- date:

## YOUR NEXT ACTIONS (required to progress)
This DP is PAUSED until you answer.
1. Optional: Ask mode or paste DIG_DEEPER into Agent.
2. To decide: `/partial-zero-answer DP=B5 VERDICT=… NOTES=…`
3. To advance after that: paste PROGRESS_NOW from STEP_OFF.md into Agent.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=B5
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
