# DP-A5 — assert_consumer skips commitment when assembly missing only

- status: closed
- created: 2026-09-21T17:15:00Z
- closed: 2026-09-21T21:26:00Z
- blocks: (resolved) MIX_JUNCTION commitment skip — A retained
- resume_hook: (closed — see decision_log)

## TL;DR (read this first)
- What’s wrong: Old code skipped generation+commitment whenever `junction_recut_precedes_mix` was True (stale-only included). **HEAD A5-1** skips only when `assembly.wav` **missing**.
- What you’d notice: Junction operating on uncommitted EDL while stale assembly exists.
- Why Partial: Commitment lies → incomplete_cut / order_drift later.
- Agent recommendation: Option **A** — retain assembly-missing-only skip.
- What that gives up: Recut never blocked by mix-era commitment (stale still asserts).

## Context (enough to decide)
- Where: `air_order.assert_consumer` for mix/junction/finalize.
- Cousin family: **MIX_JUNCTION_SEAT** (`J-assembly-freshness`).

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Retain: skip only if assembly missing | Commitment honesty | Stale path asserts harder |
| B | Skip whenever SSOT True (pre-A5) | Recut never blocked | Uncommitted EDL |
| C | Split: skip generation match, still require commitment | Middle | Two code paths |
| Defer | Live remaster commitment tape | | Delay |

## Option A — Retain A5-1 (recommended)
**What we would do:** Confirm HEAD; matrix stale-assembly still calls `verify_commitment`.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes over-broad skip cousin |
| Complexity left | Low |
| What you give up | Easy recut on stale |
| Human work | Confirm tests |
| Implement cost | Low |
| Regression risk | Low |
| Reversibility | High |

## Option B — Skip whenever SSOT
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | Reopens honesty |
| Complexity left | Low |
| What you give up | Commitment |
| Human work | None |
| Implement cost | Low |
| Regression risk | High |
| Reversibility | Easy |

## Option C — Split generation vs commitment
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium-high |
| Cousin closure | Partial |
| Complexity left | Higher |
| What you give up | Simplicity |
| Human work | Design split |
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
- Why Partial: First recut can skip; remaster with stale assembly still seals commitment.
- Honest downside: Stale remaster may fail closed until commitment heals.
- Devil’s-advocate: C is more precise but costs complexity for little Partial gain over A.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | Uncommitted junction → later mix refuse |
| Thrash tax | order_drift heal loops |
| Cousin surface area | assert_consumer + mix_seat |
| Benefit under Partial | Honest remaster |
| Replaceability | CUT over-broad SSOT skip |

## Evidence appendix
- HEAD: `src/interview_mux/air_order.py` `assert_consumer` — `skip_pre_mix_commitment = not artifact_exists(assembly.wav)`
- Hints: mechanism BP-A5; MIX_JUNCTION_SEAT; J-assembly-freshness

## Your verdict
- choice: **A**
- notes: retain HEAD A5-1; skip commitment only when assembly.wav missing; pin must_verify_commitment test; no expand
- date: 2026-09-21T21:25:00Z
- implemented: 2026-09-21T21:26:00Z

## YOUR NEXT ACTIONS
Closed. Paste PROGRESS_NOW from STEP_OFF.md for the next open DP.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=A5
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
