# DP-BUILD-MIX-JUNCTION — Mix and junction still disagree on who goes first

- status: awaiting_operator
- created: 2026-09-21T17:11:34Z
- blocks: Ironclad Partial through build→ship; mix⇄junction thrash / identical-failure halt; remaster-in-flight when mix never stamps done
- resume_hook: /partial-zero-answer DP=BUILD-MIX-JUNCTION VERDICT=…
- solution_swarm_agents: 1 (phase analyst / HEAD census; no product patches)
- aligns_with: DP-A1 (mechanism honesty); family MIX_JUNCTION_SEAT; junction J-mix-junction-precede

## TL;DR (read this first)
- What’s wrong (1–2 sentences): HEAD folded remaster-in-flight into `junction_recut_precedes_mix` (A1-1) and aligned runtime/agenda/hardening — good. Remaining: **any** unmarked mix with a landed assembly still forces junction first even when detect is clean, which traps hollow-stamp / mid-remaster Partial walks; pin/resume cousins (`mix_seat`, premature) still share the same family.
- What you’d notice in Partial: mix⇄junction ping-pong or junction looping while mix never gets a durable `.stage_done`; identical-failure ×3 on incomplete_cut / seed_order.
- Why we can’t ignore it for ironclad Partial: Build cannot exit to ship without one honest owner for “recut before first mix” vs “mix already landed, stamp or reseat.”
- Agent recommendation: Option **A** — narrow A1-1 to explicit remaster ownership + keep multi-gate SSOT; close matrix gaps.
- What that recommendation gives up: Remaster must set a clear in-flight flag (or unlink+stale) instead of relying on “assembly exists ∧ mix unmarked.”

## Context (enough to decide)
- Where in the journey (phase / stage / handoff / junction): `build` — `mix` ⇄ `junction_snip_qa`; handoffs M32/M33; J-mix-junction-precede.
- Cousin family name (plain English): **Mix vs junction seat / who-runs-first**.
- Glossary (only if needed):
  - **SSOT:** `junction_snip_qa.junction_recut_precedes_mix(ctx)`.
  - **A1-1 (HEAD):** if no live cuts, assembly present, not stale, and `not is_done("mix")` → precedes=True.
  - **MUST_PRECEDE:** junction only requires `edl` (mix never structural).

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Narrow A1-1 to explicit remaster-in-flight flag/owner; keep one SSOT all gates call | Partial certainty + remaster legal | Small protocol for remaster writers |
| B | Revert A1-1; precedes only on live cuts \| missing \| stale; remaster must mark mix or bump stale | Simpler predicate | Remaster mid-flight needs always-stale dance |
| C | Always mix-before-junction in seed; drop precedes exception (junction only post-mix) | Lowest gate complexity | Blocks first-mix recut (HINT exec_11871 class returns) |
| Defer | Soak Partial on current A1-1 + existing matrix tests | Avoid churn | Known overbreadth stays |

## Option A — Narrow remaster-in-flight (recommended)
**What we would do** (plain steps, then code pointers).
1. Replace bare `not is_done("mix")` in `junction_recut_precedes_mix` with an explicit signal (e.g. run_meta / autopsy `remaster_in_flight` set by `remaster_mix_only` / `_budgeted_remaster_mix`, cleared when mix seats + marks done).
2. Keep all gates calling only the SSOT (runtime, agenda, hardening, input check) — already true on HEAD.
3. Extend matrix tests: clean detect + assembly + unmarked mix **without** remaster flag → precedes **False** (mix first); with flag → True.
4. Document resume: `mix_seat_resume_stage` still owns post-music pin.

**Pros:** Closes overbreadth; remaster stays legal; Partial stops junction-first traps after hollow mark fail.
**Cons:** Need durable flag ownership + clear-on-success.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Strong for MIX_JUNCTION_SEAT root |
| Complexity left | Flag lifecycle only |
| What you give up | Implicit “unmarked = remaster” heuristic |
| Human work | Verdict + flag shape review |
| Implement cost | Low–medium |
| Regression risk | Medium (must not break live-cut precede) |
| Reversibility | High |

**Cousin closure if chosen:** Closes A1 overbreadth; leaves hollow-mark (DP-BUILD-HOLLOW-MIX) and freshness (DP-BUILD-ASSEMBLY-FRESHNESS) as separate.
**Tests we would add (HEAD-accurate):** Extend `test_junction_precedes_gate_matrix.py` for flag on/off; remaster sets/clears flag.

## Option B — Revert A1-1; remaster must stale or stamp
**What we would do**
1. Delete the `not is_done("mix")` remaster-in-flight branch; precedes = live \| missing \| stale only.
2. Remaster path: either leave mix done (nested remaster already unlinks marker) **and** force `mix_stale_versus_live` / seating bump, or re-mark mix immediately after nested mix seats.
3. Keep multi-gate SSOT calls.

**Pros:** Simpler boolean; matches pre-A1-1 mental model.
**Cons:** Easy to forget stale bump → mix-first deadlock with live refuse again.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium |
| Cousin closure | Partial — remaster writers must be perfect |
| Complexity left | Stale/stamp discipline |
| What you give up | Convenient unmarked-mix remaster |
| Human work | Low |
| Implement cost | Low |
| Regression risk | Medium–high (11871 class) |
| Reversibility | Easy |

**Cousin closure if chosen:** Weak unless remaster always stamps stale.
**Tests we would add (HEAD-accurate):** Remaster always makes stale or seats+marks; gate matrix without A1-1 case.

## Option C — Kill precedes; mix always before junction
**What we would do**
1. `junction_recut_precedes_mix` always False (or delete callers).
2. Mix must tolerate / soft-pass live incomplete-cuts (or operator gate) so first mix can land for junction to recut.
3. MUST_PRECEDE junction += mix.

**Pros:** One order forever.
**Cons:** Reintroduces “nobody can recut before first assembly” unless mix softens criticals — ship-bar honesty hit.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low for critical-cut tapes |
| Cousin closure | Fake — moves thrash into mix refuse |
| Complexity left | Mix soft-pass policy |
| What you give up | Pre-mix recut ladder |
| Human work | High policy |
| Implement cost | Medium |
| Regression risk | High |
| Reversibility | Medium |

**Cousin closure if chosen:** No — new mix soft-pass cousins.
**Tests we would add (HEAD-accurate):** Would need to rewrite i25 / gate matrix expectations.

## Option Defer — Soak current A1-1
**What we would do:** Run Partial Mohan; watch for junction-first when mix unmarked without remaster.
**Pros:** No code churn.
**Cons:** Overbreadth known; ironclad claim blocked.
**Trade-off table:** Partial certainty low · cousin open · complexity left high · give up schedule honesty · human low · cost zero · regression n/a · reversible yes.

## Recommendation (not a decision)
- Preferred: Option **A**
- Why this is best for **error-free Partial**: Keeps legal remaster and multi-gate agreement while stopping “unmarked mix + any assembly ⇒ junction forever.”
- Honest downside: Flag must be written/cleared in every remaster entry/exit.
- Devil’s-advocate note: Option B is smaller if remaster already always unlinks mix and can always bump stale — verify `remaster_mix_only` before choosing A.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | HINT MIX_JUNCTION_SEAT Σ≈156 across Mohan execs — high |
| Thrash tax | Hours of mix⇄junction (solver/forensics narratives) |
| Cousin surface area | Runtime/agenda/hardening/input/assert_consumer/resume |
| Benefit under Partial | High — build exit gate |
| Replaceability | Cannot CUT junction or mix; can SIMPLIFY precedes predicate |

## Evidence appendix
- HEAD code + live behavior (**SSOT / evidence**):
  - `junction_snip_qa.py:junction_recut_precedes_mix` (A1-1 branch ~621–628)
  - `homunculus/runtime.py:_seed_prereq_block` (SSOT only; no assembly short-circuit)
  - `homunculus/agenda.py:constrain_conductor_to_seed_front`
  - `llm_flow_hardening.py:maybe_require_upstream_llm_progress`
  - `air_order.py:assert_consumer` (A5-1 missing-assembly skip)
  - `tests/test_junction_precedes_gate_matrix.py` (A1-1 case True today)
- Docs / clinic / plans (**hints only** — verify or drop):
  - `mechanism_honesty_breakpoints.md` BP-A1 Decision A1-1 (implemented shape differs from “flag” — uses unmarked mix)
  - clinic `mix.possibility.md` / `junction_snip_qa.possibility.md`
- Mohan HINT only: exec_13159/13167 i11–i11g; mohan_hint_digest MIX_JUNCTION_SEAT
- Solution-swarm raw notes: `solution_swarm/DP-BUILD-MIX-JUNCTION/`

## Your verdict
- choice: A | B | C | … | Defer | custom: …
- notes:
- date:

## YOUR NEXT ACTIONS (required to progress)
This DP is PAUSED until you answer.
1. Optional: Ask mode or paste DIG_DEEPER into Agent.
2. To decide: `/partial-zero-answer DP=BUILD-MIX-JUNCTION VERDICT=… NOTES=…`
3. To advance after that: paste PROGRESS_NOW from STEP_OFF.md into Agent.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=BUILD-MIX-JUNCTION
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
