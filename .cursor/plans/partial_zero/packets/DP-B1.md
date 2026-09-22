# DP-B1 — Compound token pins mix ahead of vo_g1

- status: closed
- created: 2026-09-21T17:15:00Z
- closed: 2026-09-21T22:15:00Z
- blocks: (resolved) PIN_PREMATURE family batch A
- resume_hook: (closed — see decision_log)

## TL;DR (read this first)
- What’s wrong: Compound strings like `mix_unseated and premature_complete:vo_g1` used to pin **mix** first. **HEAD scores longest/most-specific** structured needles (B1-2 WIP) so `premature_complete:…` can beat short mix_unseated.
- What you’d notice: Heal jumps to mix while G1 open → premature cousin thrash.
- Why Partial: Wrong pin = identical-failure without product progress.
- Agent recommendation: Option **A** — retain longest/most-specific structured token wins.
- What that gives up: “Mix seating is always more fatal” absolute priority.

## Context (enough to decide)
- Where: `producer_pin_for_token` / heal_navigate.
- Cousin family: **PIN_PREMATURE** (+ VO_LADDER_PARTIAL).

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Retain scored longest/specific (HEAD) | Correct VO pin on compounds | Scoring edge cases |
| B | Always premature_complete:* first among symptoms | Simpler rule | Mix-unseated buried when alone+noise |
| C | Keep mix_unseated absolute first | Fatal seating first | G1 leapfrog |
| Defer | Wait for compound-token Partial tape | | Delay |

## Option A — Retain scored specificity (recommended)
**What we would do:** Confirm HEAD scoring; add compound `mix_unseated`+`premature_complete:vo_g1` test if thin.
**Pros:** Already HEAD; closes compound cousin.
**Cons:** Length ties need tests.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes compound pin cousin |
| Complexity left | Low |
| What you give up | Absolute mix-first |
| Human work | Add matrix case |
| Implement cost | Low |
| Regression risk | Low |
| Reversibility | High |

**Cousin closure if chosen:** PIN compound vo_g1 vs mix_unseated.
**Tests:** Extend `test_r4_premature.py` compound case.

## Option B — Always premature_complete first
**What we would do:** Check premature_class_pin before mix_unseated needles.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High for VO compounds |
| Cousin closure | Similar |
| Complexity left | Lower score logic |
| What you give up | Nuanced scoring |
| Human work | None |
| Implement cost | Low |
| Regression risk | Low-medium |
| Reversibility | High |

## Option C — mix_unseated absolute first
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | Reopens i1 compound cousin |
| Complexity left | Low |
| What you give up | VO-first heal |
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
- Preferred: Option **A** (B also acceptable if you want a simpler absolute rule — both beat C for Partial)
- Why Partial: Structured premature classes must not lose to short mix needles.
- Honest downside: Length scoring needs tests for ties.
- Devil’s-advocate: B is easier to explain to operators.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | HINT exec_13165 i1 compound |
| Thrash tax | Wrong-pin identical storms |
| Cousin surface area | producer_pin_for_token |
| Benefit under Partial | Heal lands on VO |
| Replaceability | CUT absolute mix-first |

## Evidence appendix
- HEAD: `stage_completion.py` `producer_pin_for_token` scored list (mix_unseated + premature_class_pin by length)
- Tests: `tests/test_r4_premature.py`
- Hints: mechanism BP-B1; PIN_PREMATURE

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
/partial-zero-explain-simple DP=B1
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
