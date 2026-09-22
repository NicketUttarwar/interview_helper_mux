# DP-B2 — Short-needle stage-id substring pins

- status: closed
- created: 2026-09-21T17:15:00Z
- closed: 2026-09-21T22:15:00Z
- blocks: (resolved) PIN_PREMATURE family batch A
- resume_hook: (closed — see decision_log)

## TL;DR (read this first)
- What’s wrong: Substring `"mix" in key` pinned mix on prose like “remix bed failed.” **HEAD B2-2** uses exact tokens / delimited phrases / longest exact match — not bare stage-id substring.
- What you’d notice: Heal to mix on unrelated remix/SFX prose.
- Why Partial: False pins thrash.
- Agent recommendation: Option **A** — retain exact-token pinning.
- What that gives up: Fuzzy prose recovery from free-text errors.

## Context (enough to decide)
- Where: `PRODUCER_PIN_TABLE` walk in `producer_pin_for_token`.
- Cousin family: **PIN_PREMATURE** (`J-premature-pin`).

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Retain exact / delimited tokens (HEAD) | No remix false pin | Weaker free-text |
| B | Word-boundary / min length ≥8 | Softer middle | Still fuzzy |
| C | Restore substring table | Simple recovery | False positives |
| Defer | Wait for prose-pin tape | | Delay |

## Option A — Retain exact tokens (recommended)
**Pros:** HEAD; no remix false pin.
**Cons:** Error strings need structured tokens.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes substring cousin |
| Complexity left | Low |
| What you give up | Fuzzy prose heal |
| Human work | Confirm remix test |
| Implement cost | Low |
| Regression risk | Low |
| Reversibility | High |

## Option B — Word-boundary / min length
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium-high |
| Cousin closure | Partial |
| Complexity left | Medium |
| What you give up | Simplicity of exact |
| Human work | Tune thresholds |
| Implement cost | Medium |
| Regression risk | Medium |
| Reversibility | Medium |

## Option C — Restore substring
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | Reopens |
| Complexity left | Low |
| What you give up | Pin honesty |
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
- Why Partial: Structured tokens only — no accidental mix from “remix”.
- Honest downside: Error strings must carry structured tokens.
- Devil’s-advocate: B if logs stay prose-heavy.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | Any short DELIVERY_ORDER id in prose |
| Thrash tax | Wrong producer invoke |
| Cousin surface area | PRODUCER_PIN_TABLE |
| Benefit under Partial | Stable heal |
| Replaceability | CUT bare substring |

## Evidence appendix
- HEAD: `stage_completion.py` producer_pin_for_token B2-2 block (findall tokens; no bare substring)
- Hints: mechanism BP-B2; J-premature-pin

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
/partial-zero-explain-simple DP=B2
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
