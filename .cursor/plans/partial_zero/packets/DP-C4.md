# DP-C4 — VO / MusicGen mtime leases after job stall

- status: awaiting_operator
- created: 2026-09-21T17:15:00Z
- blocks: ESR_POST_MASTER ghost wav freshness leases
- resume_hook: /partial-zero-answer DP=C4 VERDICT=…
- solution_swarm_agents: packet merge (mechanism honesty + HEAD verify); no product patches this turn

## TL;DR (read this first)
- What’s wrong: After stall, any recent `vo_pickup/synthesized/*.wav` (&lt;180s) or music assets (&lt;120s) forced lease. **HEAD C4-1** suppresses mtime leases when job status ∈ stalled/idle/error and post-master/ship context.
- What you’d notice: Cover/publish ESR-waits as if Chatterbox running after master.
- Why Partial: Ghost leases block ship.
- Agent recommendation: Option **A** — retain suppress when stalled/idle/error + post-master/ship.
- What that gives up: Protecting lagged gui_job during real synth post-master (pending_writes still protect).

## Context (enough to decide)
- Where: `thrash_hardening.expensive_stage_lease_active`.
- Cousin family: **ESR_POST_MASTER**.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Retain suppress post-master stall mtime (HEAD) | No ghost leases | Miss lagged synth |
| B | Suppress whenever job not running/starting | Broader | Pre-master synth lag |
| C | Keep ghost mtimes always | Protect lagged gui_job | Post-master stalls |
| Defer | | Wait | Delay |

## Option A — Retain C4-1 (recommended)
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes ghost-lease cousin |
| Complexity left | Low |
| What you give up | Lagged post-master synth lease |
| Human work | Confirm pending_writes cover |
| Implement cost | Low |
| Regression risk | Low-medium |
| Reversibility | High |

## Option B — Suppress whenever not running
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium-high |
| Cousin closure | Broader |
| Complexity left | May under-lease pre-master |
| What you give up | Lagged synth protection |
| Human work | Tune |
| Implement cost | Medium |
| Regression risk | Medium |
| Reversibility | Medium |

## Option C — Keep ghosts
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | Reopens |
| Complexity left | Low |
| What you give up | Ship progress |
| Human work | None |
| Implement cost | Zero |
| Regression risk | High |
| Reversibility | N/A |

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
- Why Partial: Post-master ship must not wait on VO/MusicGen mtime ghosts when job is stalled.
- Honest downside: Rely on pending_writes for true in-flight synth.
- Devil’s-advocate: B if gui_job status lies idle during real synth often.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | HINT i8 cousin vo_wavs on done finalize |
| Thrash tax | Ship ESR wait forever |
| Cousin surface area | lease mtime |
| Benefit under Partial | Ship unblocks |
| Replaceability | CUT ghost mtime lease post-master |

## Evidence appendix
- HEAD: `thrash_hardening.py` C4-1 `skip_mtime_lease` when stalled/idle/error + post-master/ship; 180s/120s still apply otherwise
- Hints: mechanism BP-C4

## Your verdict
- choice: **A** (ESR_POST_MASTER family batch with C1–C4)
- notes: retain HEAD; shared execution_status SSOT; C5 separate
- date: 2026-09-21T23:40:00Z
- implemented: 2026-09-21T23:55:00Z

## YOUR NEXT ACTIONS (required to progress)
This DP is PAUSED until you answer.
1. Optional: Ask mode or paste DIG_DEEPER into Agent.
2. To decide: `/partial-zero-answer DP=C4 VERDICT=… NOTES=…`
3. To advance after that: paste PROGRESS_NOW from STEP_OFF.md into Agent.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=C4
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
