# DP-C1 — Wrong pin still ESR-waits on fresh master.wav

- status: awaiting_operator
- created: 2026-09-21T17:15:00Z
- blocks: ESR_POST_MASTER operator wait after audible master
- resume_hook: /partial-zero-answer DP=C1 VERDICT=…
- solution_swarm_agents: packet merge (mechanism honesty + HEAD verify); no product patches this turn

## TL;DR (read this first)
- What’s wrong: i5 early-exit was pin-self-only; wrong pin (mix/delight) + committed master still waited on fresh `master.wav`. **HEAD** adds post-master family never-wait when finalize done/seed-complete + master present (and `pipeline_complete` short-circuit).
- What you’d notice: Post-master stall on `fresh:master.wav` while heal pinned to mix/delight.
- Why Partial: Ship walk never finishes without intervene.
- Agent recommendation: Option **A** — retain post-master family never-wait (HEAD C1-1).
- What that gives up: Waiting on master.wav freshness for wrong post-family pins.

## Context (enough to decide)
- Where: `should_wait_incomplete_after_conductor` / `_pin_keeps` for mix/finalize/delight.
- Cousin family: **ESR_POST_MASTER** (`J-post-master-wait`).

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Retain: post-family never-wait when master+finalize done | Unattended ship | Wrong pin advances |
| B | Drop master.wav from freshness for non-active finalize pins only | Narrower | Delight/mix still wait other sources |
| C | Leave pin-self-only i5 | Minimal | Wrong-pin wait remains |
| Defer | | Wait | Delay |

## Option A — Retain post-family never-wait (recommended)
**What we would do:** Confirm HEAD `fin_ok and post_family → None`; matrix wrong-pin+master.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes wrong-pin master wait |
| Complexity left | Low |
| What you give up | Pin-self purity |
| Human work | Wrong-pin test |
| Implement cost | Low |
| Regression risk | Low |
| Reversibility | High |

## Option B — Drop master freshness only
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium |
| Cousin closure | Partial |
| Complexity left | Medium |
| What you give up | Full family clear |
| Human work | Design |
| Implement cost | Medium |
| Regression risk | Medium |
| Reversibility | Medium |

## Option C — Pin-self only
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | Reopens |
| Complexity left | Low |
| What you give up | Ship progress |
| Human work | None |
| Implement cost | Zero |
| Regression risk | High |
| Reversibility | N/A |

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
- Why Partial: After committed master + finalize done, remaining work is ship — not ESR-wait on master mtime for mix/delight pins.
- Honest downside: Wrong pin may advance to ship heal; C2/C5 still needed.
- Devil’s-advocate: B if you fear leaping past real mix work — but fin_ok+master already implies mix era passed.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | HINT exec_13165 wrong-pin shape |
| Thrash tax | Infinite ESR wait post-master |
| Cousin surface area | ESR + pin keeps |
| Benefit under Partial | Ship continues |
| Replaceability | CUT pin-self-only wait on master |

## Evidence appendix
- HEAD: `execution_status.py` should_wait post_family block; `_pin_keeps` still lists master.wav for mix/delight (gated by early exit)
- Tests: `test_done_master_finalize_does_not_esr_wait_on_fresh_master` — extend wrong-pin
- Hints: mechanism BP-C1

## Your verdict
- choice: **A** (ESR_POST_MASTER family batch with C2–C4)
- notes: retain post-master never-wait; shared `post_master_never_wait` SSOT
- date: 2026-09-21T23:40:00Z
- implemented: 2026-09-21T23:55:00Z

## YOUR NEXT ACTIONS (required to progress)
This DP is PAUSED until you answer.
1. Optional: Ask mode or paste DIG_DEEPER into Agent.
2. To decide: `/partial-zero-answer DP=C1 VERDICT=… NOTES=…`
3. To advance after that: paste PROGRESS_NOW from STEP_OFF.md into Agent.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=C1
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
