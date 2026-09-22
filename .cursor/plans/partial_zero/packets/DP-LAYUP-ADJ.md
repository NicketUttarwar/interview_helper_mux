# DP-LAYUP-ADJ — Layup before adjudicate (order honesty)

- status: awaiting_operator
- created: 2026-09-21T17:15:00Z
- blocks: plan_rank → sound handoff without layup⇄adjudicate⇄synth pin thrash under Partial
- resume_hook: /partial-zero-answer DP=LAYUP-ADJ VERDICT=…
- solution_swarm_agents: 1 (phase analyst merge; no product patches)

## TL;DR (read this first)
- What’s wrong (1–2 sentences): Product order is layup → … → transitions → SDP → `vo_line_adjudicate` → `vo_synthesize` (`MUST_PRECEDE` + G8), but heal/premature pins, hollow adjudicate done, and layup invalidation of transitions/gap still let Partial schedule or stamp the wrong stage. Adjudicate sits in **sound** while layup seals in **plan_rank**, so journey phases look “done” while VO chain is not.
- What you’d notice in Partial: Identical seed_order / premature storms across layup, transitions, adjudicate, synth (HINT exec_13163); layup escalation blocks synth forever; or synth runs before adjudicate seal.
- Why we can’t ignore it for ironclad Partial: plan_rank is Critical Five; wrong order burns Chatterbox and rewinds ranking work.
- Agent recommendation: Option **A** — treat MUST_PRECEDE+G8 as sole order SSOT; all heal/resume pins resolve through `earliest_incomplete_must_precede` / stability block; no phase move.
- What that recommendation gives up: Keeps cross-phase split (plan_rank vs sound); does not relocate adjudicate UI-wise.

## Context (enough to decide)
- Where in the journey (phase / stage / handoff / junction): plan_rank `nugget_layup_compose` … `transitions` → sound `sound_design_plan` → `vo_line_adjudicate` → build `vo_synthesize`. Junctions `J-must-precede-vo-chain`, `J-vo-synth-stability-g8`, `J-layup-invalidate-cascade`.
- Cousin family name (plain English): **Layup / adjudicate order** (feeds `VO_LADDER_PARTIAL` + `PIN_PREMATURE`).
- Glossary (only if needed):
  - **G8:** `vo_synthesize_stability_block` — layup complete, transitions present/complete, not stale-from-layup.
  - **HEAL_ONLY_PRODUCER:** layup / adjudicate / gap recompose may heal without full rewrite — still must not leapfrog order.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Enforce MUST_PRECEDE+G8 as sole pin SSOT everywhere | Minimal product move; closes thrash | Cross-phase UX stays split |
| B | Move `vo_line_adjudicate` into plan_rank (after transitions, before sound) | Journey matches VO seal | Phase/GUI/contract churn |
| C | CUT / skip-stub adjudicate under Partial | Faster Partial | Quality / speech lint debt |
| Defer | Rely on existing MUST_PRECEDE tests only | Avoid work if live Partial clean | Leaves hollow/pin cousins open |

## Option A — Sole order SSOT (recommended)
**What we would do** (plain steps, then code pointers).
1. Audit heal_navigate / premature_cap / agenda reinject / incompleteness_resume so VO_G1 and synth resumes never land past an incomplete layup/transitions/SDP/adjudicate hole (`earliest_incomplete_must_precede` + `resolve_vo_synth_seed_resume`).
2. Keep `clear_false_layup_invalidation_on_adjudicate` only when G1 coverage green (already HEAD); expand tests for Partial.
3. Refuse `mark_done` / auto_complete mid adjudicate batch (hollow cousin — may link DP-B4 if separate).
4. Tests: synth candidate with incomplete layup → filtered to layup; incomplete adjudicate → synth deferred; transitions stale-from-layup → transitions not synth.

**Pros:** Code already has the table; Partial needs callers to obey it.
**Cons:** Does not fix BP-B1 compound pin by itself.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High for order class |
| Cousin closure | Closes synth-before-adjudicate / layup-before-synth |
| Complexity left | Pin substring cousins remain |
| What you give up | Phase diagram neatness |
| Human work | Verdict |
| Implement cost | Medium (caller census) |
| Regression risk | Medium |
| Reversibility | High |

**Cousin closure if chosen:** Order cousins of VO_LADDER / PIN.
**Tests we would add (HEAD-accurate):** Extend `test_must_precede_order.py`; Partial filter_delivery_candidates matrices for layup→…→adjudicate→synth.

## Option B — Move adjudicate into plan_rank
**What we would do**
1. Change `phases.py` sound stages; move stage id in journey UI; keep MUST_PRECEDE edges.
2. Re-home clinic / contracts.

**Pros:** Operator sees VO text seal before “Sound.”
**Cons:** Large surface; SDP currently precedes adjudicate — must reorder or split SDP.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium (order same if MUST_PRECEDE kept) |
| Cousin closure | Weak alone |
| Complexity left | High migration |
| What you give up | Stable phase IDs |
| Human work | High review |
| Implement cost | High |
| Regression risk | High |
| Reversibility | Low |

**Cousin closure if chosen:** Cosmetic unless paired with A.
**Tests we would add (HEAD-accurate):** Phase membership assertions; journey gate order.

## Option C — Skip adjudicate under Partial
**What we would do**
1. Force adjudicate disabled / skip stub + heal when `is_partially_accelerated_run`.

**Pros:** Removes one LLM thrash surface.
**Cons:** Spoken scrub / coverage floors move later or vanish; may reburn synth on bad copy.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium–high speed |
| Cousin closure | Avoidance |
| Complexity left | Lint/refuse at synth |
| What you give up | Adjudicate quality |
| Human work | Low |
| Implement cost | Low |
| Regression risk | Medium |
| Reversibility | Easy flag |

**Cousin closure if chosen:** None for layup invalidation.
**Tests we would add (HEAD-accurate):** Partial → adjudicate skip stub seed-complete; synth proceeds under G8.

## Option Defer — …
Ship with current MUST_PRECEDE tests; reopen if Partial Mohan shows order thrash. Risk: HINT pattern already strong.

## Recommendation (not a decision)
- Preferred: Option **A**
- Why this is best for **error-free Partial**: Order law already exists; Partial fails when pins ignore it.
- Honest downside: Still need DP-VO1 for ladder-complete and DP-B* for hollow/pin.
- Devil’s-advocate note: Option C is tempting if adjudicate is net-negative under Partial — only if operator accepts thinner spoken QC.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | HINT layup + adjudicate + synth storms |
| Thrash tax | Invalidation cascade + Chatterbox reburn |
| Cousin surface area | G8, MUST_PRECEDE, premature VO_G1 |
| Benefit under Partial | Stable Phase A seal |
| Replaceability | Adjudicate optional via config today |

## Evidence appendix
- HEAD code + live behavior (**SSOT / evidence**): `delivery_guardrails.MUST_PRECEDE` rows for layup…transitions…adjudicate…synth; `vo_synthesize_stability_block`; `phases.py` sound=`sound_design_plan`,`vo_line_adjudicate`; tests `test_must_precede_order.py`.
- Docs / clinic / plans (**hints only**): clinic maps layup / transitions / adjudicate; forensic plans “complete adjudicate before synth.”
- Mohan HINT only: exec_13163 synth+adjudicate; exec_13159 layup/transitions.
- Solution-swarm raw notes: `solution_swarm/DP-LAYUP-ADJ/` (none yet)

## Your verdict
- choice: **A**
- notes: MUST_PRECEDE+G8 sole order SSOT; expand VO chain producers; clamp heal/resume on VO clamp stages; no phase move
- date: 2026-09-21T23:10:00Z
- implemented: 2026-09-21T23:25:00Z

## YOUR NEXT ACTIONS (required to progress)
This DP is PAUSED until you answer.
1. Optional: Ask mode or paste DIG_DEEPER into Agent.
2. To decide: `/partial-zero-answer DP=LAYUP-ADJ VERDICT=… NOTES=…`
3. To advance after that: paste PROGRESS_NOW from STEP_OFF.md into Agent.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=LAYUP-ADJ
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
