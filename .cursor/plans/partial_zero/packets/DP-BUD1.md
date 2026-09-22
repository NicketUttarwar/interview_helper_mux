# DP-BUD1 — Max-invokes / attempt_memo refuse after a root fix (hollow “Finished”)

- status: implemented
- created: 2026-09-21T22:59:00Z
- decided: 2026-09-21T23:04:00Z
- implemented: 2026-09-21T23:14:00Z
- blocks: none (resume Partial on `exec_13168`)
- resume_hook: /partial-zero-progress
- solution_swarm_agents: companion classify after DP-GAP-PICKUP-CONFIRM A land (no swarm)

## TL;DR (read this first)
- What’s wrong: After **DP-GAP-PICKUP-CONFIRM A** (ownership stamp) loaded, `gap_framing_compose` still never produces `gap_report`. The dispatch door refuses with `max_invokes_per_identity` / `attempt_memo` (budget burned during the pre-fix AuthorityDenied thrash). The job then logs **“Finished: Interviewer script”** and advances — hollow success.
- What you’d notice in Partial: Rapid analysis “complete” loops; `dispatch refused … advancing`; still no `understanding/gap_report.json`; premature_complete heal pins back to compose.
- Why we can’t ignore it for ironclad Partial: Root ownership fix cannot be proven; fill_gaps stays blocked forever once the door cap is spent.
- Agent recommendation: Option **A** — on product/code fingerprint change (or logged implement), reset identity attempt counters + attempt_memo for the healed producer; **refuse must not emit stage-success Finished**.
- What that recommendation gives up: Pure “never reset budget” hardness after every thrash (you allow a one-shot reclaim after a real product delta).

## Context (enough to decide)
- Where: **fill_gaps** · `gap_framing_compose` · dispatch door (`dispatch_door.py`) · defect ledger · homunculus ledger attempts.
- Cousin family: **BUDGET_THRASH** (soak gate named in STEP_OFF / PRE-PARTIAL).
- Prior closed root: **DP-GAP-PICKUP-CONFIRM A** — AuthorityDenied on `flow_adaptation` is fixed; latest logs no longer show that deny.
- Glossary: **attempt_memo** = door refuses re-dispatch without product progress token change; **max_invokes_per_identity** = hard cap (here **3**) on stage dispatches.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Fingerprint/product-delta reclaim + refuse≠Finished | Unblocks same-run proof after real fixes | Must define reclaim trigger carefully |
| B | Raise / special-case Partial caps only | Quick Partial relief | Masks thrash; Full-auto still burns |
| C | Manual operator clear of ledger/memo after each DP (status quo) | No code | Easy to miss; thrash resumes |
| Defer | More census of door refuse→Finished paths | Broader map | Leaves exec_13168 stuck |

## Option A — Reclaim after product delta + honest refuse (recommended)
**What we would do:**
1. When `product_code_fingerprint` (or ownership matrix version) flips vs the memo/defect stamp, clear `max_invokes` / `attempt_memo` counters for identities blocked by the healed class (at least `gap_framing_compose` here).
2. When dispatch door refuses, do **not** emit GUI/job success “Finished: \<stage title\>”; leave `error`/`incomplete` so premature_complete heal is honest.
3. HEAD tests: refuse path does not mark job complete success; fingerprint flip reclaims one identity’s attempt budget.

**Pros:** Same-run Partial can prove the ownership fix; stop hollow Finished lies.  
**Cons:** Reclaim rules must not open infinite thrash (tie to fingerprint / logged DP only).

**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes BUDGET residual for post-fix resume + hollow Finished |
| Complexity left | Medium (fingerprint wire + job status honesty) |
| What you give up | Absolute never-reset caps |
| Human work | Verdict |
| Implement cost | Medium |
| Regression risk | Medium (reclaim too broad → thrash) |
| Reversibility | High |

**Cousin closure if chosen:** BUDGET_THRASH resume-after-fix; hollow Finished on refuse.  
**Tests:** `MUX_FORENSICS=0` — door refuse ≠ job success; fingerprint flip resets identity attempts.

## Option B — Raise Partial-only caps
**What we would do:** Higher `max_invokes_per_identity` under partially-accelerated only.  
**Pros:** Cheap.  
**Cons:** Does not fix hollow Finished; Full-auto still stuck; invites longer thrash.

## Option C — Manual clear forever
**What we would do:** Document companion clears of defect/ledger/memo after each implement (what we tried).  
**Pros:** No product change.  
**Cons:** Operational tax; attempt_memo / live door still racing; not ironclad.

## Option Defer — …
Census all refuse→Finished paths before coding. Safer inventory; run stays paused.

## Recommendation (not a decision)
- Preferred: Option **A**
- Why this is best for **error-free Partial**: Ownership fix is landed but unprovable until the door allows a real compose; hollow Finished hides that.
- Honest downside: Reclaim must be tightly gated to fingerprint/DP land — not “any retry”.
- Devil’s-advocate note: B looks faster but leaves the honesty hole that made this stall look “green”.

## Cut economics
| Factor | Notes |
|--------|-------|
| Bug recurrence | Every thrash-then-fix resume |
| Thrash tax | High (rapid refuse loops on exec_13168) |
| Cousin surface area | Door + job status + ledger |
| Benefit under Partial | Unblocks fill_gaps proof |
| Replaceability | KEEP door; SIMPLIFY refuse→Finished |

## Evidence appendix
- HEAD / live `exec_13168`:
  - Serve recycled; `confirm_pickup_speaker` stamp present (`stage_key=missing_framing`).
  - `gui_log`: `dispatch refused gap_framing_compose: max_invokes_per_identity — advancing` then `Finished: Interviewer script`; no `gap_report`; `.stage_done/gap_framing_compose` missing.
  - Cap observed: `attempt_cap("gap_framing_compose") == 3`.
  - Prior AuthorityDenied thrash burned attempts before A land.
- Docs/plans (**hints**): STEP_OFF soak → DP-BUD1; PRE-PARTIAL residual.
- Mohan HINT only: this Partial run (not forensics reopen).

## Your verdict
- choice: **A**
- notes: (none)
- date: 2026-09-21T23:04:00Z

## YOUR NEXT ACTIONS (required to progress)
Implemented. Companion watch same `exec_13168` — prove `gap_report` lands without hollow Finished.
1. Paste PROGRESS_NOW into Agent on stall / gate.
2. Do not start forensics.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
```
/partial-zero-progress
Read .cursor/plans/partial_zero/STEP_OFF.md and decision_queue.md.
Next unit: companion watch exec_13168 fill_gaps / gap_framing_compose after DP-BUD1 A.
Goal: error-free partially_accelerated without forensics.
Do not patch unless implementing a logged verdict. Do not start forensics.
```
