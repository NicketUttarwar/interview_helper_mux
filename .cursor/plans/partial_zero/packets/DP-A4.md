# DP-A4 — Seed sticky fail-open on freeze fingerprint

- status: closed
- created: 2026-09-21T17:15:00Z
- closed: 2026-09-21T20:40:00Z
- blocks: (resolved) FREEZE sticky seed — A thorough
- resume_hook: (closed — see decision_log)
- solution_swarm_agents: packet merge (mechanism honesty + HEAD verify); no product patches this turn

## TL;DR (read this first)
- What’s wrong: Exception path in `_hard_freeze_and_edl_done` once treated any freeze `fingerprint` as hard sticky — soft freeze could sticky-complete framing/layup/SDP. **HEAD already requires `hard` / level hard** (never fingerprint-alone).
- What you’d notice: Soft freeze + probe error → framing/SDP marked done without hard seal.
- Why Partial cares: False sticky skips real work; later hollow/prematurity.
- Agent recommendation: Option **A** — retain HEAD (hard evidence only).
- What that gives up: Fail-open unstick on probe error without hard stamp.

## Context (enough to decide)
- Where: Seed-order under freeze; `FREEZE_STICKY_SEED_STAGES`.
- Cousin family: **FREEZE_CONSTITUTION**.
- Glossary: Sticky = treat stage satisfied without running it.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Retain: sticky only on hard / level hard | Honesty | Rare probe may not sticky |
| B | Restore fingerprint-alone fail-open | Never stick seed on probe error | Soft→sticky lie |
| C | On probe error never sticky | Fail closed both ways | May rewind framing under hard freeze |
| Defer | Wait for probe-error tape | Rare path | Unconfirmed |

## Option A — Retain hard-only sticky (recommended)
**What we would do:** Confirm `seed_policy.py` exception path without fingerprint-alone; add soft-fingerprint-not-sticky test if missing.
**Pros:** Already HEAD; Partial-safe.
**Cons:** Probe error without hard stamp won’t sticky.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes soft-fingerprint cousin |
| Complexity left | Low |
| What you give up | Aggressive unstick |
| Human work | Confirm test |
| Implement cost | Low |
| Regression risk | Low |
| Reversibility | High |

## Option B — Restore fingerprint fail-open
**What we would do:** Re-add `or fr.get("fingerprint")` in exception path.
**Pros:** Matches old “unstick seed” intent.
**Cons:** Soft freeze sticky lie.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | Reopens honesty cousin |
| Complexity left | Low code |
| What you give up | Freeze level honesty |
| Human work | None |
| Implement cost | Low |
| Regression risk | Medium |
| Reversibility | Easy |

## Option C — Never sticky on probe error
**What we would do:** Exception path always returns False (forensics may still raise).
**Pros:** No false sticky.
**Cons:** Hard freeze + EDL done may still rewind sticky stages if probe fails.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium |
| Cousin closure | Partial |
| Complexity left | Low |
| What you give up | Sticky under probe fail |
| Human work | Ops may re-run framing |
| Implement cost | Low |
| Regression risk | Medium |
| Reversibility | High |

## Option Defer
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | None |
| Complexity left | Unchanged |
| What you give up | Confirm rare path |
| Human work | Watch |
| Implement cost | Zero |
| Regression risk | Zero |
| Reversibility | N/A |

## Recommendation (not a decision)
- Preferred: Option **A**
- Why Partial: Sticky only with hard evidence — no soft fingerprint greenwash.
- Honest downside: Rare probe failures may not unstick.
- Devil’s-advocate: C is stricter; A matches campaign “hard evidence” without rewinding hard freezes when artifact proves hard.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | Rare but catastrophic false complete |
| Thrash tax | Later premature on sticky-skipped work |
| Cousin surface area | seed_policy only |
| Benefit under Partial | Honest seed skip |
| Replaceability | CUT fingerprint-alone |

## Evidence appendix
- HEAD: `src/interview_mux/seed_policy.py` `_hard_freeze_and_edl_done` exception path — `fr.get("hard")` or level `hard`/`hard_freeze` only
- Hints: mechanism BP-A4; FREEZE_CONSTITUTION
- Test hint: soft-only fingerprint not sticky still worth a matrix row

## Your verdict
- choice: **A (thorough)**
- notes: hard-only SSOT; soft/fingerprint never; config extras for future stages; matrix soft/hard/probe/contradictory level
- date: 2026-09-21T20:35:00Z
- implemented: 2026-09-21T20:40:00Z

## YOUR NEXT ACTIONS
Closed. Paste PROGRESS_NOW from STEP_OFF.md for the next open DP.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=A4
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
