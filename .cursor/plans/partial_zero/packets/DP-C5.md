# DP-C5 — Five meanings of done (ship-bar vocabulary)

- status: awaiting_operator
- created: 2026-09-21T17:15:00Z
- blocks: SHIP_BAR_VOCAB; ESR vs driver vs agenda vs G-Publish
- resume_hook: /partial-zero-answer DP=C5 VERDICT=…
- solution_swarm_agents: packet merge (mechanism honesty + HEAD verify); no product patches this turn

## TL;DR (read this first)
- What’s wrong: ESR no-wait, runner batch complete, driver `pipeline_complete`, agenda `ship_after_master_remaining`, and G-Publish consent can disagree at one wall-clock. **HEAD** documents `pipeline_complete(ctx)` as ship-bar SSOT (master+cover+audio.mp3+markers); G-Publish/S3 is not that bar.
- What you’d notice: Local package ready while ESR thrash, or S3 advisory hang looks like pipeline failure.
- Why Partial: Need one operator-visible DONE for unattended close.
- Agent recommendation: Option **A** — retain `pipeline_complete` as ship-bar SSOT; keep G-Publish separate consent; make ESR/driver consult it (HEAD already short-circuits should_wait when pipeline_complete).
- What that gives up: Treating S3 sync as part of Partial complete.

## Context (enough to decide)
- Where: `execution_status.pipeline_complete`; driver; agenda remaining; G-Publish.
- Cousin family: **SHIP_BAR_VOCAB** (consumes B5, C1–C4).

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Retain pipeline_complete ship-bar SSOT (HEAD C5-2) | One local DONE | S3 not in bar |
| B | Document five predicates as intentional layers; only close C1–C4 | Less product fight | Vocab still split |
| C | Treat G-Publish hang as ESR class | Force remote | Wrong product surface |
| Defer | | Wait | Delay |

## Option A — pipeline_complete SSOT (recommended)
**What we would do:** Confirm HEAD; ensure driver/ESR/agenda docs point here; matrix asserts Partial complete == pipeline_complete.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes ship-bar vocab root |
| Complexity left | Low if consulted everywhere |
| What you give up | S3-in-DONE |
| Human work | Align docs/tests |
| Implement cost | Low-medium |
| Regression risk | Low |
| Reversibility | High |

## Option B — Document layers only
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium |
| Cousin closure | Weak — C1–C4 only |
| Complexity left | Vocab debt remains |
| What you give up | One DONE |
| Human work | Docs |
| Implement cost | Zero |
| Regression risk | Low |
| Reversibility | N/A |

## Option C — Fold G-Publish into ESR
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low for product |
| Cousin closure | Wrong cousin |
| Complexity left | Consent UX mess |
| What you give up | Advisory separation |
| Human work | High |
| Implement cost | High |
| Regression risk | High |
| Reversibility | Hard |

## Option Defer
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | None |
| Complexity left | Unchanged |
| What you give up | Product choice |
| Human work | Watch |
| Implement cost | Zero |
| Regression risk | Zero |
| Reversibility | N/A |

## Recommendation (not a decision)
- Preferred: Option **A**
- Why Partial: One local ship bar Partial can finish without S3/consent; ESR already short-circuits on pipeline_complete.
- Honest downside: Remote publish remains a separate operator gate.
- Devil’s-advocate: B if you want minimal product change — but then operators still ask “are we done?”

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | podcast_publish spam / local vs S3 (HINT) |
| Thrash tax | False incomplete after local package |
| Cousin surface area | five predicates |
| Benefit under Partial | Clear DONE |
| Replaceability | CUT treating G-Publish as ESR |

## Evidence appendix
- HEAD: `execution_status.pipeline_complete`; driver delegates; should_wait returns None if pipeline_complete
- Hints: mechanism BP-C5 Decision C5-2; SHIP_BAR_VOCAB; J-post-master-wait

## Your verdict
- choice: **A**
- notes: pipeline_complete sole Partial DONE; package_ready envelope; G-Publish/S3 never in bar
- date: 2026-09-22T00:10:00Z
- implemented: 2026-09-22T00:25:00Z

## YOUR NEXT ACTIONS (required to progress)
This DP is PAUSED until you answer.
1. Optional: Ask mode or paste DIG_DEEPER into Agent.
2. To decide: `/partial-zero-answer DP=C5 VERDICT=… NOTES=…`
3. To advance after that: paste PROGRESS_NOW from STEP_OFF.md into Agent.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=C5
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
