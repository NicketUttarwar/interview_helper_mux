# DP-SHIP-HOLLOW-FINALIZE — Hollow master_finalize mark_done / missing PMQ

- status: awaiting_operator
- created: 2026-09-21T17:10:00Z
- blocks: Ironclad Partial through `master_finalize` → SHIP_AFTER_MASTER; false ship-ready or AuthorityDenied thrash after loudnorm
- resume_hook: /partial-zero-answer DP=SHIP-HOLLOW-FINALIZE VERDICT=…
- solution_swarm_agents: phase analyst merge (options A–C + Defer); devil’s-advocate in Recommendation

## TL;DR (read this first)
- What’s wrong (1–2 sentences): Finalize “done” means different things: agenda/`assert_may_mark_done` require **master.wav + PMQ**, but `stage_artifact_incompleteness` checks **master integrity only**, and **force heal `_mark_done_raw` bypasses** hollow assert — so Partial can thrash on refuse **or** hollow-stamp without PMQ. i11h persisted PMQ before delight re-raise (surface); root split remains.
- What you’d notice in Partial: `authority_denied:mark_done:hollow:master_finalize` with master on disk; or `.stage_done/master_finalize` without `post_master_quality.json`; ship stages / ESR disagree.
- Why we can’t ignore it for ironclad Partial: Ship is Critical Five; hollow finalize lies about NORTH_STAR publishability and feeds ESR/driver five-meanings-of-done cousins.
- Agent recommendation: Option **A** — one finalize-complete predicate (master + PMQ + integrity) used by incompleteness, force-done, mark_done, and ESR ship-pin clear.
- What that recommendation gives up: Force-heal shortcuts that stamped finalize on master alone; slightly stricter ship advance.

## Context (enough to decide)
- Where in the journey (phase / stage / handoff / junction): phase **ship** / `master_finalize` → packaging; junctions **J-hollow-done**, **J-post-master-wait**.
- Cousin family name (plain English): **Hollow done at finalize / PMQ** (HOLLOW_DONE · feeds SHIP_BAR_VOCAB / ESR_POST_MASTER).
- Glossary (only if needed):
  - **PMQ:** `master/post_master_quality.json` — publish envelope after authoritative delight.
  - **`_mark_done_raw`:** heal force path that skips `assert_may_mark_done`.
  - **i11h surface:** persist PMQ even when delight loud-fails; flush pending on stage exception.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Unify finalize-complete = master+PMQ+integrity everywhere | Family-root; Partial honesty | Touches heal force + incompleteness + ESR |
| B | Keep i11h persist/flush; only document the split | Cheap | Force-raw hollow stamp still possible |
| C | Treat master.wav alone as finalize-complete; PMQ async | Faster ship advance | Breaks publishability / NORTH_STAR gate |
| Defer | Soak Partial ship with HEAD i11h | Avoid churn | Leaves force-raw hole |

## Option A — Unify finalize-complete SSOT (recommended)
**What we would do** (plain steps, then code pointers).
1. Add one helper (e.g. `finalize_outputs_complete(ctx)`) ≡ committed master integrity ∧ PMQ artifact present (schema/status optional second phase).
2. Wire into:
   - `stage_artifact_incompleteness("master_finalize")`
   - `assert_may_force_done` / heal path (no `_mark_done_raw` stamp without helper)
   - keep `assert_may_mark_done` / `stage_outputs_present` aligned (already master+PMQ)
3. ESR ship-pin clear: prefer `seed_stage_complete` / helper over bare `is_done` (may require companion verdict on DP-B5 — note in implement packet).
4. Keep i11h order: persist PMQ before delight re-raise; flush pending on exception.
5. Tests: missing PMQ → incompleteness + force refuse + mark_done raise; delight fail still leaves PMQ on disk; no raw hollow stamp.

**Pros:** One meaning of finalize-done; closes hollow thrash and hollow greenwash.
**Cons:** Broader than i11h; may need B5 follow-up for ESR.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High for finalize honesty |
| Cousin closure | Closes finalize hollow surfaces; feeds SHIP_BAR close |
| Complexity left | ESR five-meanings still need C5 |
| What you give up | Lenient force-heal after loudnorm-only |
| Human work | Verdict; optional B5 linkage |
| Implement cost | Medium |
| Regression risk | Medium (heal force paths) |
| Reversibility | High if helper centralized |

**Cousin closure if chosen:** HOLLOW_DONE finalize/PMQ row; reduces i11h class; does not alone close DP-C5.
**Tests we would add (HEAD-accurate):** Extend `test_i11_pmq_persists_when_delight_fails`; new force-heal refuse without PMQ; incompleteness asserts PMQ missing.

## Option B — i11h surface only; leave force-raw / incompleteness split
**What we would do**
1. Keep current `run_post_master_quality` persist-before-delight-raise + wrapped flush.
2. Document that force heal must not be used on finalize without PMQ (comment/clinic only).
3. Rely on normal `mark_done` AuthorityDenied raise (B4-2 already on HEAD).

**Pros:** Tiny scope; already tested.
**Cons:** `_mark_done_raw` hollow stamp remains a live hole; incompleteness lies to FORCE_DONE_GUARDED.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium |
| Cousin closure | Surface only |
| Complexity left | High |
| What you give up | Root honesty |
| Human work | Low |
| Implement cost | None / docs |
| Regression risk | Low |
| Reversibility | N/A |

**Cousin closure if chosen:** Weak.
**Tests we would add (HEAD-accurate):** None required beyond existing i11h.

## Option C — Master-only finalize-complete; PMQ best-effort
**What we would do**
1. Change agenda required outputs / mark_done to master.wav only.
2. Run PMQ as soft follow-on; ship packaging may re-enter PMQ via playbook.

**Pros:** Fewer hollow refuses after loudnorm.
**Cons:** Violates publishability contract; Partial can package without ship gate; NORTH_STAR listen-delight undermined.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | False positive “done” |
| Cousin closure | Creates worse ship-bar cousins |
| Complexity left | High |
| What you give up | Authoritative delight at ship |
| Human work | High product risk |
| Implement cost | Medium |
| Regression risk | High |
| Reversibility | Painful once packaging trusts it |

**Cousin closure if chosen:** Anti-pattern — do not.
**Tests we would add (HEAD-accurate):** Would need contract rewrite tests — not recommended.

## Option Defer — …
Ship a Partial soak with HEAD i11h; reopen if hollow finalize or missing-PMQ stamp reappears.

**Trade-off:** Force-raw hole stays until then.

## Recommendation (not a decision)
- Preferred: Option **A**
- Why this is best for **error-free Partial**: Finalize cannot lie or thrash; packaging only sees honest PMQ+master.
- Honest downside: May stall ship until delight/PMQ path succeeds — correct for Partial zero.
- Devil’s-advocate note: Unifying incompleteness might make more stages “incomplete” mid-failure (good); ensure exception flush still leaves PMQ so retry can mark_done without re-loudnorm.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | HINT i11h; surface patched |
| Thrash tax | Hollow mark_done loop mid-ship |
| Cousin surface area | J-hollow-done · J-post-master-wait · B5 · C5 |
| Benefit under Partial | Unblocks ship Critical Five |
| Replaceability | Cannot CUT PMQ; SIMPLIFY predicates |

## Evidence appendix
- HEAD code + live behavior (**SSOT / evidence**):
  - `agenda.STAGE_REQUIRED_OUTPUTS["master_finalize"]` = master.wav + post_master_quality.json
  - `stage_completion` incompleteness for finalize = `committed_master_integrity_ok` only
  - `heal_or_refuse_mark` force → `_mark_done_raw=True` bypasses `assert_may_mark_done`
  - `assert_may_force_done` uses incompleteness only
  - `post_master_quality.run_post_master_quality` persist then re-raise delight
  - `write_staging.run_wrapped_stage` flush pending on exception
- Docs / clinic / plans (**hints only**): clinic master_finalize map; BP-B4/B5 (B4 raise already on HEAD — verify); forensics i11h
- Mohan HINT only: exec_13167 i11h hollow mark_done after loudnorm, PMQ missing
- Solution-swarm raw notes: (merged in-packet)

## Your verdict
- choice: A | B | C | … | Defer | custom: …
- notes:
- date:

## YOUR NEXT ACTIONS (required to progress)
This DP is PAUSED until you answer.
1. Optional: Ask mode or paste DIG_DEEPER into Agent.
2. To decide: `/partial-zero-answer DP=SHIP-HOLLOW-FINALIZE VERDICT=… NOTES=…`
3. To advance after that: paste PROGRESS_NOW from STEP_OFF.md into Agent.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=SHIP-HOLLOW-FINALIZE
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
