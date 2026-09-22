# DP-B3 — Unknown premature_complete class is a fake stage

- status: closed
- created: 2026-09-21T17:15:00Z
- closed: 2026-09-21T22:15:00Z
- blocks: (resolved) PIN_PREMATURE family batch A
- resume_hook: (closed — see decision_log)

## TL;DR (read this first)
- What’s wrong: Unknown `premature_complete:brand_new_class` used to return that string as a pin (not in DELIVERY_ORDER). **HEAD B3-1** returns `transitions` for unknown classes.
- What you’d notice: Heal navigates to a non-stage; thrash/halt.
- Why Partial: Fake stages break seed-order.
- Agent recommendation: Option **A** — retain unknown→`transitions` (safe default).
- What that gives up: Forward-compat auto-pin for new class names without code.

## Context (enough to decide)
- Where: `premature_class_pin`.
- Cousin family: **PIN_PREMATURE**.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Retain unknown → transitions (HEAD) | Safe default | May over-pin transitions |
| B | Allowlist only; else None fallthrough | Strictest | More fallthrough bugs |
| C | Keep return-cls (forward compat) | New classes without code | Fake stages |
| Defer | | Wait | Delay |

## Option A — Retain unknown→transitions (recommended)
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes fake-stage cousin |
| Complexity left | Low |
| What you give up | Forward-compat auto pin |
| Human work | Unknown-class test |
| Implement cost | Low |
| Regression risk | Low |
| Reversibility | High |

## Option B — Allowlist only → None
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Stricter |
| Complexity left | Need allowlist maint |
| What you give up | Default pin |
| Human work | Maintain _PREMATURE_NAMED_CLASSES |
| Implement cost | Low-medium |
| Regression risk | Medium |
| Reversibility | High |

## Option C — Return cls
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
- Why Partial: Never invent stage ids; transitions is the bare premature home.
- Honest downside: Unknown typos go to transitions (visible, fixable).
- Devil’s-advocate: Mechanism advice preferred allowlist→None (B); A is already HEAD and Partial-safe.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | Typos / new classes |
| Thrash tax | Non-stage pin |
| Cousin surface area | premature_class_pin |
| Benefit under Partial | Safe heal |
| Replaceability | CUT return-cls |

## Evidence appendix
- HEAD: `stage_completion.py` premature_class_pin — unknown cls → `transitions`
- Hints: mechanism BP-B3

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
/partial-zero-explain-simple DP=B3
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
