# DP-A3 — Gap / SDP writes that skip seat freeze

- status: closed
- created: 2026-09-21T17:15:00Z
- closed: 2026-09-21T20:20:00Z
- blocks: (resolved) FREEZE_CONSTITUTION writers — A′′ Global Freeze
- resume_hook: (closed — see decision_log)
- solution_swarm_agents: packet merge (mechanism honesty + HEAD verify); no product patches this turn

## TL;DR (read this first)
- What’s wrong: Historically many gap/SDP/transitions writers skipped End-A. HEAD now routes optimizer promotes and gap commit through `persist_frozen_seat_doc` / `frozen_seat_write_allowed` — but not every cousin writer is proven End-A-closed.
- What you’d notice in Partial: Silent seat fingerprint drift after freeze, or sudden `authority_denied` mid-optimizer.
- Why we can’t ignore it: Freeze is meaningless if SDP/gap can mutate seats silently.
- Agent recommendation: Option **A** — every seat-affecting gap/selection/SDP persist under freeze: End-A or skip-write (complete the HEAD path).
- What that recommendation gives up: Ungated Take-best / cue-number convenience under freeze.

## Context (enough to decide)
- Where: Timeline optimizer Take-best; adjudicate; soundscape verify; omit_ledger heals.
- Cousin family: **FREEZE_CONSTITUTION** (feeds SDP_CUE_SLOTS).
- Glossary: **skip-write** = leave prior doc; do not expand WAV demand (H-3).

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Every seat-affecting persist: End-A or skip-write | Freeze honesty for Partial | Metadata writes need classification |
| B | Gate only fingerprint-changing ids; allow cue metadata | Less thrash on SDP numbers | Classification bugs |
| C | Trust ownership ALLOW only; leave writers | Minimal churn | Seat freeze not enforced |
| Defer | Census remaining writers first | Safer inventory | Delay close |

## Option A — End-A or skip-write everywhere seat-affecting (recommended)
**What we would do:** Finish census; wire remaining writers (`vo_line_adjudicate` seat-id changes, `soundscape_verify` SDP seat fields, etc.) through `persist_frozen_seat_doc` / `frozen_seat_write_allowed`. Optimizer already uses it.
**Pros:** Matches freeze as seat constitution; Partial predictable.
**Cons:** Must classify seat vs metadata carefully.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes A3 writer cousins |
| Complexity left | Medium census leftover |
| What you give up | Ungated promotes |
| Human work | Review allowlist reasons |
| Implement cost | Medium |
| Regression risk | Medium |
| Reversibility | High |

**Cousin closure if chosen:** FREEZE writer surface; SDP promote under freeze.
**Tests:** Optimizer under freeze refuse/skip; gap commit skip metric; SDP cue-only path per B if split later.

## Option B — Fingerprint-changing only
**What we would do:** Gate seated/omitted/orientation ids; allow metadata/sanitize/SDP cue numbers without End-A.
**Pros:** Less false refuse on cue trim.
**Cons:** Easy to misclassify a seat-expanding write as metadata.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium-high |
| Cousin closure | Partial — cue cousins remain policy |
| Complexity left | Higher classifier complexity |
| What you give up | Simple fail-closed |
| Human work | Define field classes |
| Implement cost | Medium-high |
| Regression risk | Medium-high |
| Reversibility | Medium |

**Cousin closure if chosen:** Seat-id cousins only.
**Tests:** Cue-number write allowed; seat-id refuse.

## Option C — Ownership ALLOW only
**What we would do:** Leave as ownership matrix; no seat freeze on those paths.
**Pros:** Cheap.
**Cons:** Freeze paper lie.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | None |
| Complexity left | High honesty debt |
| What you give up | Freeze meaning |
| Human work | None now |
| Implement cost | Zero |
| Regression risk | Low short-term |
| Reversibility | N/A |

## Option Defer — Finish writer census first
**What we would do:** Expand caller table before verdict.
**Pros:** Avoid over-gating.
**Cons:** Known optimizer path already fixed; delay.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low until census |
| Cousin closure | None |
| Complexity left | Unchanged |
| What you give up | Speed to law |
| Human work | Census agent |
| Implement cost | Zero code |
| Regression risk | Zero |
| Reversibility | N/A |

## Recommendation (not a decision) — post-census + global freeze ask
- Preferred: **custom A′′ (Global Freeze)** — A′ choke-point, but freeze is **app-global** (no cue carve-out; write-layer enforcement).
- Details: [analysis/dp_a3_writer_census.md](../analysis/dp_a3_writer_census.md)
  1. Gate at `maybe_admit_hot_write` / commit_* so raw writes cannot bypass.
  2. Under freeze: FROZEN docs (+ seat-truth: air_script vo_seats / omit stamps) → End-A or skip only.
  3. SDP cue trim under freeze → skip / advisory placement_adjustments (not a metadata allow).
  4. Fail-closed adjudicate + GUI (End-A or one-shot); ban `_one_writer_raw` under freeze outside tests.
  5. Allowlist pass for must-land reasons; fingerprint as test oracle.
- Why: “Global freeze” fails if any caller can raw-write; B’s cue carve-out fights global.
- Honest downside: More skip/advisory under freeze; Take-best / bed trim no-op unless named End-A.
- Still better than plain A: choke-point is the thoroughness upgrade plain A lacked.

## Your verdict
- choice: **custom:A′′ (Global Freeze)**
- notes: write-layer choke; End-A or skip; seat-truth; fail-closed; allowlist pass
- date: 2026-09-21T20:05:00Z
- implemented: 2026-09-21T20:25:00Z

## YOUR NEXT ACTIONS
Closed. Paste PROGRESS_NOW from STEP_OFF.md for the next open DP.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)
