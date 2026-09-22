# DP-SOUND-SDP-CUE — Soundscape cue_slots thrash (dens vs planned beds)

- status: done
- created: 2026-09-21T17:10:00Z
- decided: 2026-09-21T18:55:00Z
- landed: 2026-09-21T18:55:00Z
- blocks: Ironclad Partial through `sound_design_plan` / sound→build music+SFX consumers; identical-failure / heal-validate↔stage-fail loops on theme_underscore beds
- resume_hook: /partial-zero-implement DP=SOUND-SDP-CUE
- verdict: custom A+ (one writer + invent soft-block + normalize/dedupe)

## Operator picks (logged)
- One `build_cue_slots_ssot` writer (dens ∪ planned ∪ inject)
- Fold repair inject into `admit_inject_cue_slots`
- Invent unpaid soft-block keeps planned/inject beds (no wipe)
- Canonical `normalize_cue_slot` + identity dedupe (planned > inject > dens)

## Landed
- `soundscape_policy.py`: normalize / merge / SSOT / invent soft-block / admit_inject
- `artifact_repairs.py`: inject via `admit_inject_cue_slots` only
- tests: `test_soundscape_policy.py` + F-03 soft-block wording (`MUX_FORENSICS=0`)

## TL;DR (read this first)
- What’s wrong (1–2 sentences): `cue_slots` have **three writers** (dens scorer, planned-SDP merge, repair inject) plus an **invent gate that zeroes slots**. Dens-cap wipe of planned beds was the exec_13167 storm; HEAD merges planned beds and isolates refresh failure, but invent wipe + dual inject/refresh can still disagree with post-commit validate.
- What you’d notice in Partial: `sound_design_plan` heals “pass” then stage fails (or identical theme_underscore thrash); music/SFX see sparse slots after refresh.
- Why we can’t ignore it for ironclad Partial: HINT dominant family on exec_13167; sound phase is Critical Five — Partial cannot walk past thrashing SDP.
- Agent recommendation: Option **A** — single cue_slot SSOT helper (score ∪ planned ∪ inject rules) + invent gate must not erase already-planned SDP beds.
- What that recommendation gives up: Broader soundscape_policy change; invent-gate “empty while unpaid” becomes nuanced (preserve planned, still block heuristic invent).

## Context (enough to decide)
- Where in the journey (phase / stage / handoff / junction): phase **sound** / `sound_design_plan` (+ fill_gaps `soundscape_policy_build` producer); handoffs M14/M29/P10; junction **J-sdp-cue-slots**.
- Cousin family name (plain English): **SDP cue_slots / dens honesty** (`SDP_CUE_SLOTS`).
- Glossary (only if needed):
  - **dens max_beds:** density budget that caps scored bed slots.
  - **planned beds:** non-skipped `under_segment` theme beds already in SDP flow_plans.
  - **invent unpaid:** deferred musical invent still owed to `sound_design_plan` → gate sets `cue_slots=[]`.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | One SSOT builder for cue_slots; invent gate preserves planned beds | Family-root close; Partial certainty | Medium implement across score/refresh/repair |
| B | Keep i3 surface patches; add matrix soak only | Cheap; trust dens-merge + inject isolate | Invent wipe + dual writers remain |
| C | Stop refreshing at SDP start; repair-only inject | Less mid-stage churn | Stale policy vs selection; music consumers drift |
| Defer | Wait for live Partial soak on Mohan | Avoid churn if i3 enough | Risk re-open identical storm |

## Option A — Single cue_slot SSOT (recommended)
**What we would do** (plain steps, then code pointers).
1. Centralize slot construction in `soundscape_policy` (e.g. `build_cue_slots_ssot`): dens score → merge planned SDP beds → apply inject rules (palette∩slot) → volley bind → optional [:N] compact **after** merge.
2. `refresh_cue_slots` and `artifact_repairs` call that helper only (no ad-hoc `policy["cue_slots"]=` forks).
3. Change `_apply_invent_obligation_gate`: while unpaid, still zero **heuristic** density / underscore invent, but **retain** slots with `reason` in `{planned_sdp_bed, theme_underscore_*}` (or re-merge planned after wipe).
4. Ownership: all policy persists keep `stage_key=soundscape_policy_build` (already on refresh commit path).
5. Tests: dens cap + planned beds; invent unpaid + planned beds survive; repair inject idempotent; SDP flush does not drop injects.

**Pros:** Closes family at root; one mental model for Partial.
**Cons:** Touches invent semantics (product-visible: unpaid invent no longer means empty slots).
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes dens wipe, inject/refresh fork, invent erase cousins |
| Complexity left | Low after SSOT lands |
| What you give up | Strict “empty slots while invent unpaid” storytelling |
| Human work | Verdict on invent+planned interaction |
| Implement cost | Medium |
| Regression risk | Medium (music dens / invent_gate consumers) |
| Reversibility | High if helper feature-flagged |

**Cousin closure if chosen:** SDP_CUE_SLOTS → closed-when matrix green; reduces FREEZE cousin noise on SDP rewrite thrash.
**Tests we would add (HEAD-accurate):** Extend `test_soundscape_policy.py` invent+planned; repair idempotence; flush survival already present — keep under `MUX_FORENSICS=0`.

## Option B — Declare i3 patches sufficient; soak-only
**What we would do**
1. Keep `_merge_planned_bed_slots`, refresh `write_committed_json` + stage_key, inject isolate.
2. Add Partial soak checklist / identical-failure histogram gate; no invent-gate change.
3. Document dual writers as intentional layers.

**Pros:** Minimal code; tests already exist.
**Cons:** Invent wipe still clears planned; repair can still fork slots after refresh; family stays “open” honestly.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium-low |
| Cousin closure | Weak — surfaces only |
| Complexity left | High (three writers) |
| What you give up | Root honesty |
| Human work | Low |
| Implement cost | Low (docs/soak) |
| Regression risk | Low |
| Reversibility | N/A |

**Cousin closure if chosen:** None until soak proves quiet.
**Tests we would add (HEAD-accurate):** Optional soak harness only.

## Option C — No refresh at SDP start; repair-only
**What we would do**
1. Remove `refresh_cue_slots` from `run_sound_design_plan` build_input.
2. Rely on `soundscape_policy_build` initial score + post-SDP repair inject.
3. Keep dens-merge for when refresh is called from repairs/operator.

**Pros:** Removes hottest thrash call site.
**Cons:** Selection drift mid-pipeline not reconciled before LLM; music brief may see stale slots; thrash moves to repair/validate loop.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low–medium |
| Cousin closure | Moves cousin, does not close |
| Complexity left | High |
| What you give up | Pre-LLM policy freshness |
| Human work | Low |
| Implement cost | Low |
| Regression risk | Medium (stale slots in LLM packet) |
| Reversibility | Easy |

**Cousin closure if chosen:** Incomplete.
**Tests we would add (HEAD-accurate):** Assert SDP build_input does not call refresh; repair still injects.

## Option Defer — …
Wait for a Partial (non-forensics) Mohan run through sound with current HEAD. Reopen packet if identical SDP_CUE_SLOTS reappears.

**Trade-off:** Saves implement cost; risks burning another long run on known family.

## Recommendation (not a decision)
- Preferred: Option **A**
- Why this is best for **error-free Partial**: One builder removes heal-pass/stage-fail disagreement; invent gate no longer fights planned beds.
- Honest downside: Invent-gate product nuance must be reviewed.
- Devil’s-advocate note: If invent unpaid, showing planned beds might greenwash “musical direction complete” — mitigate with explicit `invent_gate=blocked` flags (already present) and incompleteness on unpaid invent, not empty slots.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | HINT very high (exec_13167); surface patched, root open |
| Thrash tax | Identical-failure storm class |
| Cousin surface area | J-sdp-cue-slots · freeze SDP write · music consumers |
| Benefit under Partial | Unblocks Critical Five sound |
| Replaceability | Refresh cannot be CUT; SIMPLIFY to SSOT |

## Evidence appendix
- HEAD code + live behavior (**SSOT / evidence**):
  - `soundscape_policy.score_cue_slots` dens cap + `_merge_planned_bed_slots`
  - `refresh_cue_slots` committed write `stage_key=soundscape_policy_build`
  - `_apply_invent_obligation_gate` → `cue_slots=[]` when unpaid
  - `stages/sound_design_stages.py` refresh in build_input
  - `artifact_repairs` refresh isolate + inject_theme_underscore_cue_slot
- Docs / clinic / plans (**hints only** — verify or drop): clinic SDP map; forensics i3; cousin_matrix SDP_CUE_SLOTS
- Mohan HINT only: exec_13167 ~655 primary SDP_CUE_SLOTS; intervene i3
- Solution-swarm raw notes: (merged in-packet; no separate swarm folder)

## Your verdict
- choice: A | B | C | … | Defer | custom: …
- notes:
- date:

## YOUR NEXT ACTIONS (required to progress)
This DP is PAUSED until you answer.
1. Optional: Ask mode or paste DIG_DEEPER into Agent.
2. To decide: `/partial-zero-answer DP=SOUND-SDP-CUE VERDICT=… NOTES=…`
3. To advance after that: paste PROGRESS_NOW from STEP_OFF.md into Agent.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=SOUND-SDP-CUE
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
