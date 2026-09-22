# DP-B4 — mark_done silent AuthorityDenied → hollow success

- status: awaiting_operator
- created: 2026-09-21T17:15:00Z
- blocks: HOLLOW_DONE; LLM auto_complete lies
- resume_hook: /partial-zero-answer DP=B4 VERDICT=…
- solution_swarm_agents: packet merge (mechanism honesty + HEAD verify); no product patches this turn

## TL;DR (read this first)
- What’s wrong: `mark_done` used to log+return on AuthorityDenied; callers treated success. **HEAD raises AuthorityDenied**; `llm_flow_hardening` catches → False.
- What you’d notice: Logs say complete; no `.stage_done`; later premature_complete.
- Why Partial: Hollow advance is campaign poison.
- Agent recommendation: Option **A** — retain raise + callers check (HEAD).
- What that gives up: Silent GUI soft-fail without stage error surfaces.

## Context (enough to decide)
- Where: `run_context.mark_done`; LLM hardening; runner/GUI.
- Cousin family: **HOLLOW_DONE** (`J-hollow-done`).

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Retain raise AuthorityDenied (HEAD) | Loud honesty | GUI must catch |
| B | Return bool; never raise | Softer API | Easy to ignore bool |
| C | Silent log return (pre-fix) | Never crash path | Hollow lie |
| Defer | | Wait | Delay |

## Option A — Retain raise (recommended)
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes hollow mark cousin |
| Complexity left | Low if all callers catch |
| What you give up | Silent soft paths |
| Human work | Audit callers |
| Implement cost | Low leftover |
| Regression risk | Medium if uncaught |
| Reversibility | High |

## Option B — bool return
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium-high |
| Cousin closure | Similar if enforced |
| Complexity left | API churn |
| What you give up | Raise discipline |
| Human work | Migrate callers |
| Implement cost | Medium |
| Regression risk | Medium (ignored bool) |
| Reversibility | Medium |

## Option C — Silent return
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | Reopens |
| Complexity left | Low |
| What you give up | Done honesty |
| Human work | None |
| Implement cost | Low |
| Regression risk | High |
| Reversibility | Easy |

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
- Why Partial: Cannot greenwash refused stamps; hardening already returns False.
- Honest downside: Uncaught raise = stage error (desired for Partial).
- Devil’s-advocate: B if you want no exceptions across GUI — but ignore-bool is the classic hollow cousin.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | HINT i4/i11/i11h |
| Thrash tax | premature after fake complete |
| Cousin surface area | mark_done + LLM envelope |
| Benefit under Partial | Real done |
| Replaceability | CUT silent swallow |

## Evidence appendix
- HEAD: `run_context.py` mark_done raises AuthorityDenied; `llm_flow_hardening.py` returns False on catch
- Hints: mechanism BP-B4; HOLLOW_DONE

## Your verdict
- choice: A | B | C | Defer | custom: …
- notes:
- date:

## YOUR NEXT ACTIONS (required to progress)
This DP is PAUSED until you answer.
1. Optional: Ask mode or paste DIG_DEEPER into Agent.
2. To decide: `/partial-zero-answer DP=B4 VERDICT=… NOTES=…`
3. To advance after that: paste PROGRESS_NOW from STEP_OFF.md into Agent.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=B4
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
