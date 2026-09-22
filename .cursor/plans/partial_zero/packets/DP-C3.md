# DP-C3 — Driver wait helper parity when master missing

- status: awaiting_operator
- created: 2026-09-21T17:15:00Z
- blocks: ESR_POST_MASTER caller split pre-master
- resume_hook: /partial-zero-answer DP=C3 VERDICT=…
- solution_swarm_agents: packet merge (mechanism honesty + HEAD verify); no product patches this turn

## TL;DR (read this first)
- What’s wrong: Driver once called raw `wait_vs_halt` when master missing while pipeline/agenda/runner used `should_wait`. **HEAD** uses `should_wait_incomplete_after_conductor` on that path (C3-1); lease_stage remains resume target.
- What you’d notice: Pre-master incomplete-after-conductor waits differently in driver vs runner.
- Why Partial: Split callers → nondeterministic wait/halt.
- Agent recommendation: Option **A** — retain always `should_wait_incomplete_after_conductor` + lease resume.
- What that gives up: Driver-only aggressive lease-wait design.

## Context (enough to decide)
- Where: `tools/full_auto_driver.py` incomplete-after-conductor; `execution_status.should_wait_*`.
- Cousin family: **ESR_POST_MASTER**.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Retain one helper everywhere (HEAD) | Parity | Less driver special-case |
| B | Keep driver raw wait_vs_halt when master missing | Aggressive pre-master wait | Caller split |
| C | should_wait but always honor lease_stage execute-from | Same as A explicit | Docs only if HEAD already |
| Defer | | Wait | Delay |

## Option A — Retain one helper (recommended)
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes caller-split cousin |
| Complexity left | Low |
| What you give up | Driver special lease aggression |
| Human work | Parity test |
| Implement cost | Low |
| Regression risk | Low |
| Reversibility | High |

## Option B — Raw wait_vs_halt pre-master
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | Reopens split |
| Complexity left | Low |
| What you give up | Parity |
| Human work | None |
| Implement cost | Low |
| Regression risk | High |
| Reversibility | Easy |

## Option C — Explicit lease resume + should_wait
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Same as A |
| Complexity left | Doc clarity |
| What you give up | Nothing if HEAD done |
| Human work | Confirm lease_stage |
| Implement cost | Low |
| Regression risk | Low |
| Reversibility | High |

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
- Preferred: Option **A** (C synonymous if lease resume already wired)
- Why Partial: One wait meaning across driver/pipeline/agenda/runner.
- Honest downside: Driver cannot be “more aggressive” than ESR.
- Devil’s-advocate: B only if Partial needs longer pre-master leases than should_wait allows.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | Pre-master incomplete-after-conductor |
| Thrash tax | Halt vs wait disagreement |
| Cousin surface area | driver vs ESR |
| Benefit under Partial | Deterministic wait |
| Replaceability | CUT raw wait_vs_halt path |

## Evidence appendix
- HEAD: `tools/full_auto_driver.py` ~9066 imports `should_wait_incomplete_after_conductor`
- Hints: mechanism BP-C3 narrowed

## Your verdict
- choice: **A** (ESR_POST_MASTER family batch with C1–C4)
- notes: retain HEAD; shared execution_status SSOT; C5 separate
- date: 2026-09-21T23:40:00Z
- implemented: 2026-09-21T23:55:00Z

## YOUR NEXT ACTIONS (required to progress)
This DP is PAUSED until you answer.
1. Optional: Ask mode or paste DIG_DEEPER into Agent.
2. To decide: `/partial-zero-answer DP=C3 VERDICT=… NOTES=…`
3. To advance after that: paste PROGRESS_NOW from STEP_OFF.md into Agent.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=C3
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
