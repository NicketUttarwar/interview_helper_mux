# DP-GAP-PICKUP-CONFIRM — Pickup auto-confirm writes flow_adaptation under the wrong stage

- status: implemented
- created: 2026-09-21T22:45:00Z
- decided: 2026-09-21T22:46:00Z
- implemented: 2026-09-21T22:50:00Z
- blocks: (resolved) — resume Partial exec_13168 after operator clears thrash pause
- resume_hook: /partial-zero-progress (resume same run)
- solution_swarm_agents: companion classify on live Partial stall (no swarm)

## TL;DR (read this first)
- What’s wrong: `maybe_auto_confirm_pickup_speaker` → `confirm_pickup_speaker` persists `understanding/flow_adaptation.json` **without** `stage_key="missing_framing"`. When the active stage is `gap_framing_compose`, ownership correctly denies the write (`owner=missing_framing`).
- What you’d notice in Partial: `AuthorityDenied` on gap compose → no `gap_report` → analysis soft-fill loops → delivery `premature_complete:phase_a_edl` ×N → HARD needs_operator at `topic_coverage_audit` (PIN to that stage is **correct**; not a pin bug).
- Why we can’t ignore it for ironclad Partial: fill_gaps never produces VO script; plan_rank/delivery cannot honestly advance.
- Agent recommendation: Option **A** — stamp `stage_key="missing_framing"` on pickup/adaptation writers that are legally owned by missing_framing; declare the path on missing_framing StageInfo.
- What that recommendation gives up: Convenience of “active-stage inherits stage_key” for these helpers (they must name the owning producer).

## Context (enough to decide)
- Where in the journey: **fill_gaps** · handoff `missing_framing` → `gap_framing_compose` · junction ownership ALLOW for `flow_adaptation.json`.
- Cousin family name (plain English): **OWNERSHIP_STAGE_KEY** (artifact ownership honesty — wrong active stage on co-owned persist).
- Not: PIN_PREMATURE (closed) — heal pin to `topic_coverage_audit` without selection is right.
- Not: DP-BUD1 alone — budget halt is the **symptom** after ×20+ premature thrash.
- Glossary: **active stage** = `write_staging` / `assert_write` stage when `stage_key` omitted.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Always `stage_key="missing_framing"` on confirm/patch writers (+ StageInfo declare) | Small honest fix; keep ALLOW narrow | Helpers must name owner |
| B | Add `gap_framing_compose` as ALLOW co-owner of `flow_adaptation` | Quick unblock | Widens writer surface forever |
| C | Only auto-confirm under `missing_framing`; compose must not call it | Clear stage boundaries | Risk compose runs with unconfirmed pickup |
| Defer | Census all bare `flow_adaptation` writes first | Broader map | Leaves Partial stuck |

## Option A — Stamp owning stage_key (recommended)
**What we would do:**
1. `confirm_pickup_speaker` / `apply_flow_adaptation_patch` (and cousins in `gap_fill_eligibility` that mutate overrides) pass `stage_key="missing_framing"` (or `source_topology_build` when that is the true author).
2. Declare `understanding/flow_adaptation.json` on missing_framing `StageInfo` so flush doesn’t drop staged writes (`undeclared_owned_staging_path` already seen on this run).
3. HEAD test: under active `gap_framing_compose`, `maybe_auto_confirm_pickup_speaker` persists without `AuthorityDenied`; gap compose can proceed.

**Pros:** Matches ALLOW SSOT; no new producers; fixes root of exec_13168 stall.  
**Cons:** Must audit other bare `write_json(flow_adaptation)` call sites (`tbiy_conformance.refresh_conformance`, operator skip, etc.) as cousins in same implement or follow-on.

**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes pickup-confirm surface; other bare writers may remain |
| Complexity left | Low–medium (small census) |
| What you give up | Implicit stage_key inheritance for these helpers |
| Human work | Verdict only |
| Implement cost | Low |
| Regression risk | Low |
| Reversibility | High |

**Cousin closure if chosen:** OWNERSHIP_STAGE_KEY pickup path; optional follow-on for `refresh_conformance` mirrored write.  
**Tests we would add (HEAD-accurate):** `tests/test_*` — auto-confirm under fake active `gap_framing_compose` ALLOW; missing_framing StageInfo lists flow_adaptation (`MUX_FORENSICS=0`).

## Option B — Widen ALLOW to gap_framing_compose
**What we would do:** Add `gap_framing_compose` to ALLOW row for `understanding/flow_adaptation.json`.  
**Pros:** Unblocks compose without touching confirm helpers.  
**Cons:** Compose becomes a permanent co-author of adaptation; more freeze/ownership cousins later.

**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium |
| Cousin closure | Weak — paper over wrong writer |
| Complexity left | Higher long-term |
| What you give up | Narrow ownership |
| Human work | Low |
| Implement cost | Trivial |
| Regression risk | Medium (who may mutate overrides) |
| Reversibility | Medium |

## Option C — Confirm only inside missing_framing
**What we would do:** Remove `maybe_auto_confirm_pickup_speaker` from the `gap_framing_compose` / `optimal_questions` branch in `pipeline._run_single_stage_impl`; ensure missing_framing always confirms before done; compose assumes confirmed.  
**Pros:** Stage boundary clarity.  
**Cons:** If missing_framing marked done without confirm (hollow / skip paths), compose still blocks on `require_gap_path_clear` — need a second heal path.

**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium-high if missing_framing is airtight |
| Cousin closure | Partial |
| Complexity left | Medium (done/confirm coupling) |
| What you give up | Late auto-confirm convenience |
| Human work | Medium review |
| Implement cost | Medium |
| Regression risk | Medium |
| Reversibility | High |

## Option Defer — …
Census all `flow_adaptation` writers before any patch. Safe inventory; leaves this Partial run blocked until another answer.

## Recommendation (not a decision)
- Preferred: Option **A**
- Why this is best for **error-free Partial**: Root call site is proven in `gui_log` traceback; ALLOW already names the right owner; stamp it.
- Honest downside: Other bare writers (`refresh_conformance`, `operator_skip_gap_fill`) may need the same pattern in the same implement or a tiny follow-on DP.
- Devil’s-advocate note: B is faster but teaches “widen ALLOW when active stage disagrees” — bad habit vs ownership SSOT.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | Immediate on Partial with auto-accept + framing enabled |
| Thrash tax | ×20+ premature + identical analysis/delivery |
| Cousin surface area | Small writer set |
| Benefit under Partial | Unblocks fill_gaps → plan_rank |
| Replaceability | N/A — KEEP helpers; SIMPLIFY stage_key |

## Evidence appendix
- HEAD code + live behavior (**SSOT / evidence**):
  - `pipeline.py` ~411–425: on `gap_framing_compose`, calls `maybe_auto_confirm_pickup_speaker`
  - `source_topology.py` `confirm_pickup_speaker` ~956: `ctx.write_json("understanding/flow_adaptation.json", adapt)` — **no stage_key**
  - `artifact_ownership.py` ALLOW: `flow_adaptation` → `source_topology_build` + `missing_framing` only
  - Live `exec_13168` `gui_log.jsonl`: traceback AuthorityDenied exactly on that path; `gap_report` absent; identical `delivery:premature_complete:phase_a_edl` ×26; HARD thrash ×24 pin `topic_coverage_audit`
- Docs / clinic / plans (**hints only**): PIN_PREMATURE closed; soak listed BUDGET as symptom — do not open DP-BUD1 as root.
- Mohan HINT only: this is **this** Partial run, not forensics reuse.
- Solution-swarm raw notes: n/a (companion packet)

## Your verdict
- choice: **A**
- notes: (none)
- date: 2026-09-21T22:46:00Z

## YOUR NEXT ACTIONS (required to progress)
Implemented. Resume Partial on the same run.
1. Clear needs_operator / resume Partial driver on `exec_13168` (from `gap_framing_compose` / analysis).
2. Paste PROGRESS_NOW if you want companion re-attach after resume.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
```
/partial-zero-progress
Read .cursor/plans/partial_zero/STEP_OFF.md and decision_queue.md.
RUN=exec_13168_d19c15b58ab4_20260921T211330Z
Next unit: resume Partial after DP-GAP-PICKUP-CONFIRM A; companion classify stalls only.
Goal: error-free partially_accelerated without forensics.
Do not patch unless implementing a logged verdict. Do not start forensics.
```
