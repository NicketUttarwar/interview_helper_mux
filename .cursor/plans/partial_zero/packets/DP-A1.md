# DP-A1 — Junction-before-mix gates disagree

- status: implemented (folded into DP-MIX-JUNCTION-SEAT-AUTHORITY)
- created: 2026-09-21T17:15:00Z
- decided: 2026-09-21T17:42:41Z
- implemented: 2026-09-21T17:55:00Z
- blocks: MIX_JUNCTION_SEAT family close; remaster mid-flight Partial walks
- resume_hook: (done)
- solution_swarm_agents: packet merge (mechanism honesty + HEAD verify); no product patches this turn

## TL;DR (read this first)
- What’s wrong (1–2 sentences): Historically runtime short-circuited on `assembly.wav` while agenda/hardening obeyed `junction_recut_precedes_mix` — remaster with unmarked mix could pin-pong. **HEAD already folded remaster-in-flight into the SSOT** (A1-1 WIP) and deleted the assembly short-circuit.
- What you’d notice in Partial: Without one SSOT, mix⇄junction identical-failure / seed_order_prereq thrash mid-remaster.
- Why we can’t ignore it for ironclad Partial: Unattended Partial cannot survive disagreeing precede gates.
- Agent recommendation: Option **A** — confirm/retain HEAD A1-1 (SSOT owns remaster-in-flight; all callers use one function).
- What that recommendation gives up: Ability to “quickly allow junction” via a one-off runtime escape; remaster semantics live in SSOT forever.

## Context (enough to decide)
- Where in the journey: Delivery remaster — `junction_snip_qa` vs `mix` after assembly exists but mix unmarked.
- Cousin family name: **MIX_JUNCTION_SEAT** (junction `J-mix-junction-precede`).
- Glossary: **SSOT** = `junction_recut_precedes_mix(ctx)` — True on live incomplete-cuts, missing/stale assembly, or remaster-in-flight (`not is_done("mix")` with landed assembly).

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Retain HEAD: remaster-in-flight inside SSOT; no runtime short-circuit | One precede truth for Partial | SSOT slightly more stateful |
| B | Revert to assembly.wav runtime short-circuit (pre-A1-1) | Remaster “feels fast” from runtime alone | Gate disagreement returns |
| C | Delete remaster-in-flight; force mix-first whenever assembly present + clean detect | Simplest true/false | Remaster stuck until mix re-marked |
| Defer | Wait for live Partial remaster tape | Avoid confirming WIP | Partial ships with unconfirmed seat law |

## Option A — Retain HEAD A1-1 (recommended)
**What we would do:** Operator confirms current code as Partial law. Keep `junction_recut_precedes_mix` remaster branch; runtime/agenda/hardening only call SSOT. Matrix-test “assembly present + mix unmarked + clean detect.”
**Pros:** Already on HEAD; closes gate disagreement; remaster stays legal.
**Cons:** SSOT must stay the only escape hatch.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High — one precede predicate |
| Cousin closure | Closes MIX_JUNCTION_SEAT precede cousin |
| Complexity left | Low if tests lock matrix |
| What you give up | Ad-hoc runtime escapes |
| Human work | Verdict + matrix review |
| Implement cost | Low (tests only if gaps) |
| Regression risk | Low if tests cover remaster |
| Reversibility | High — can revert SSOT branch |

**Cousin closure if chosen:** J-mix-junction-precede callers agree.
**Tests we would add (HEAD-accurate):** Extend `tests/test_junction_precedes_gate_matrix.py` for assembly-present+mix-unmarked; keep `test_i25_*`.

## Option B — Revert runtime assembly short-circuit
**What we would do:** Restore `if ctx.artifact_exists("master/assembly.wav"): return None` in `_seed_prereq_block`; remove remaster-in-flight from SSOT (or leave SSOT False on that case).
**Pros:** Matches old remaster comment (exec_11130).
**Cons:** Agenda/hardening still pin mix first → thrash.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low — known disagreement |
| Cousin closure | Reopens thrash cousin |
| Complexity left | High (two laws) |
| What you give up | Gate honesty |
| Human work | Debug thrash again |
| Implement cost | Medium (revert + tests) |
| Regression risk | High |
| Reversibility | Easy revert of revert |

**Cousin closure if chosen:** None — reopens BP-A1.
**Tests:** Would need to encode the split (bad for Partial).

## Option C — Mix-first whenever assembly present + clean
**What we would do:** SSOT returns False when no live/stale/missing; delete remaster-in-flight True branch. Remaster must re-mark mix or stamp stale explicitly before junction.
**Pros:** Simplest boolean.
**Cons:** Remaster unlink of mix done leaves junction blocked until operator/heal marks mix.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium — simple but remaster pain |
| Cousin closure | Partial close of disagree; remaster cousin open |
| Complexity left | Low code; high ops |
| What you give up | Unattended remaster |
| Human work | More unlocks |
| Implement cost | Low–medium |
| Regression risk | Medium (remaster flows) |
| Reversibility | High |

**Cousin closure if chosen:** Disagreement closed; remaster-in-flight cousin remains operational.
**Tests:** Remaster fixture must expect mix first.

## Option Defer — Wait for live remaster Partial
**What we would do:** Leave confirmation open; no matrix expand.
**Pros:** No decision fatigue.
**Cons:** WIP law unconfirmed for campaign closeout.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low for campaign close |
| Cousin closure | None |
| Complexity left | Unchanged |
| What you give up | Preemptive ironclad |
| Human work | Watch runs |
| Implement cost | Zero now |
| Regression risk | Zero now |
| Reversibility | N/A |

## Recommendation (not a decision)
- Preferred: Option **A**
- Why this is best for **error-free Partial**: One precede function all gates share; remaster stays unattended-legal without forensics pin-pong.
- Honest downside: SSOT must stay carefully maintained.
- Devil’s-advocate note: Option C is simpler boolean math — but Partial remaster of unmarked mix is common enough that dying for simplicity fails the campaign.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | High if dual gates return |
| Thrash tax | mix⇄junction 5-min loops (HINT exec_11871 class) |
| Cousin surface area | Agenda + hardening + runtime + air_order |
| Benefit under Partial | Unattended remaster |
| Replaceability | Short-circuit is CUT; remaster branch is KEEP inside SSOT |

## Evidence appendix
- HEAD code + live behavior (**SSOT / evidence**):
  - `src/interview_mux/junction_snip_qa.py` `junction_recut_precedes_mix` — remaster-in-flight when `not live and not missing and not stale` and `not is_done("mix")` → True
  - `src/interview_mux/homunculus/runtime.py` `_seed_prereq_block` — calls SSOT only (comment A1-1; no assembly short-circuit)
  - Callers: `homunculus/agenda.py`, `llm_flow_hardening.py`, `stage_input_checks.py`, `air_order.py` (A5 skip separate)
- Docs / clinic / plans (**hints only**): `mechanism_honesty_breakpoints.md` BP-A1; `cousin_matrix.md` MIX_JUNCTION_SEAT; `junction_register.md` J-mix-junction-precede
- Mohan HINT only: remaster / exec_11871 class — verify on HEAD tests
- Solution-swarm raw notes: (none required; A1 is confirm-retain)

## Your verdict
- choice: A | B | C | Defer | custom: …
- notes:
- date:

## YOUR NEXT ACTIONS (required to progress)
This DP is PAUSED until you answer.
1. Optional: Ask mode or paste DIG_DEEPER into Agent.
2. To decide: `/partial-zero-answer DP=A1 VERDICT=… NOTES=…`
3. To advance after that: paste PROGRESS_NOW from STEP_OFF.md into Agent.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=A1
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
