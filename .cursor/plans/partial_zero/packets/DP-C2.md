# DP-C2 — Driver keep-join requires is_done forever

- status: awaiting_operator
- created: 2026-09-21T17:15:00Z
- blocks: ESR_POST_MASTER infinite join on stalled finalize
- resume_hook: /partial-zero-answer DP=C2 VERDICT=…
- solution_swarm_agents: packet merge (mechanism honesty + HEAD verify); no product patches this turn

## TL;DR (read this first)
- What’s wrong: Driver stalled path used to keep-joining forever unless `is_done(stage)`. **HEAD** adds `stalled_expensive_can_advance` / advance toward ship when master committed (C2).
- What you’d notice: Finalize stalled, master on disk, driver never advances ship.
- Why Partial: Operator-visible infinite join.
- Agent recommendation: Option **A** — retain advance if master committed ∧ (is_done ∨ ship remaining ∨ stage in ship set).
- What that gives up: Maximum caution against killing live remaster.

## Context (enough to decide)
- Where: `tools/full_auto_driver.py` stalled path; `execution_status.stalled_expensive_can_advance`.
- Cousin family: **ESR_POST_MASTER**.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Retain stalled advance when master committed (HEAD) | Never infinite join | May leave remaster mid-flight |
| B | Advance only on is_done (pre-C2) | Safer remaster | Infinite join returns |
| C | Time-box keep-join then heal_navigate | Wall-clock cap | Arbitrary timeout |
| Defer | | Wait | Delay |

## Option A — Retain stalled advance (recommended)
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes infinite keep-join |
| Complexity left | Low |
| What you give up | Ultra-safe remaster join |
| Human work | Stalled finalize test |
| Implement cost | Low |
| Regression risk | Medium |
| Reversibility | High |

## Option B — is_done only
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | Reopens |
| Complexity left | Low |
| What you give up | Ship progress |
| Human work | None |
| Implement cost | Low |
| Regression risk | High |
| Reversibility | Easy |

## Option C — Time-box then heal
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium |
| Cousin closure | Partial |
| Complexity left | Timeout policy |
| What you give up | Evidence-based advance |
| Human work | Tune seconds |
| Implement cost | Medium |
| Regression risk | Medium |
| Reversibility | Medium |

## Option Defer
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | None |
| Complexity left | Unchanged |
| What you give up | Confirm |
| Human work | Watch |
| Implement cost | Zero |
| Regression risk | Zero |
| Reversibility | N/A |

## Recommendation (not a decision)
- Preferred: Option **A**
- Why Partial: Master committed + stall must not keep-join forever; ship remaining is enough signal.
- Honest downside: Pre-master leapfrog guarded in HEAD — keep that guard.
- Devil’s-advocate: C if advance predicates feel too magical.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | Stalled finalize + hollow refuse mark_done |
| Thrash tax | Infinite join |
| Cousin surface area | driver + ESR |
| Benefit under Partial | Ship finishes |
| Replaceability | CUT forever keep-join |

## Evidence appendix
- HEAD: `execution_status.stalled_expensive_can_advance` / `stalled_expensive_advance_stage`; driver incomplete-after-conductor uses should_wait
- Hints: mechanism BP-C2

## Your verdict
- choice: **A** (ESR_POST_MASTER family batch with C1–C4)
- notes: retain HEAD; shared execution_status SSOT; C5 separate
- date: 2026-09-21T23:40:00Z
- implemented: 2026-09-21T23:55:00Z

## YOUR NEXT ACTIONS (required to progress)
This DP is PAUSED until you answer.
1. Optional: Ask mode or paste DIG_DEEPER into Agent.
2. To decide: `/partial-zero-answer DP=C2 VERDICT=… NOTES=…`
3. To advance after that: paste PROGRESS_NOW from STEP_OFF.md into Agent.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=C2
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
