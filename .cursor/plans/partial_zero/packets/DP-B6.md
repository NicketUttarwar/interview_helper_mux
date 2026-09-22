# DP-B6 — Two incompleteness_resume_stage defs (dead shadow)

- status: closed
- created: 2026-09-21T17:15:00Z
- closed: 2026-09-21T22:15:00Z
- blocks: (resolved) PIN_PREMATURE family batch A
- resume_hook: (closed — see decision_log)

## TL;DR (read this first)
- What’s wrong: First `(reason, *, stage_id="")` def used substring table without `premature_class_pin` and was shadowed. **HEAD has a single** `(ctx, consumer_stage)` def.
- What you’d notice: Future caller of wrong signature silently wrong pins.
- Why Partial: Maintenance hazard reopens pin cousins.
- Agent recommendation: Option **A** — retain single live API (confirm delete).
- What that gives up: Prose-only resume helper unless renamed explicitly.

## Context (enough to decide)
- Where: `stage_completion.incompleteness_resume_stage`.
- Cousin family: **PIN_PREMATURE**.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Retain single (ctx, stage) API | No dead shadow | Lose prose helper |
| B | Merge: rename prose helper explicitly | Keep both uses | Two APIs |
| C | Restore dead first def | Compat | Hazard |
| Defer | | Wait | Delay |

## Option A — Retain single API (recommended)
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes dead-def hazard |
| Complexity left | Low |
| What you give up | Prose helper |
| Human work | Grep callers |
| Implement cost | Zero |
| Regression risk | Low |
| Reversibility | High |

## Option B — Explicit dual named APIs
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Same + prose |
| Complexity left | Two names |
| What you give up | One function |
| Human work | Docs |
| Implement cost | Low |
| Regression risk | Low |
| Reversibility | High |

## Option C — Restore shadow
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | Reopens |
| Complexity left | Low |
| What you give up | Safety |
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
- Why Partial: One resume API; premature_class_pin always in play.
- Honest downside: Prose callers need another name if needed later (B).
- Devil’s-advocate: B if external tools called the old signature.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | Accidental wrong overload |
| Thrash tax | Wrong pin |
| Cousin surface area | stage_completion |
| Benefit under Partial | Maintainability |
| Replaceability | CUT dead def |

## Evidence appendix
- HEAD: only one `def incompleteness_resume_stage(ctx, consumer_stage)` in `stage_completion.py`
- Hints: mechanism BP-B6

## Your verdict
- choice: **A** (PIN family batch with B1/B2/B3/B6)
- notes: retain HEAD; matrix test_pin_premature_family.py
- date: 2026-09-21T22:05:00Z
- implemented: 2026-09-21T22:15:00Z

## YOUR NEXT ACTIONS
Closed. Paste PROGRESS_NOW from STEP_OFF.md.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=B6
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
