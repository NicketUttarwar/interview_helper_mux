# DP-VO1 — VO ladder honesty under Partial

- status: closed
- created: 2026-09-21T17:15:00Z
- closed: 2026-09-21T21:45:00Z
- blocks: (resolved) VO ladder Partial — A+ landed; cousins NESTED-SYNTH / LAYUP-ADJ / B1 remain
- resume_hook: (closed — see decision_log)

## TL;DR (read this first)
- What’s wrong (1–2 sentences): Several surfaces disagree on “VO path ready / ladder complete” — `vo_path_ready`, G1 journey clear, G8 layup/transitions stability, adjudicate seed-complete, nested mint skip, and `require_vo_path_ready(..., auto_accept=True)` on `vo_synthesize`. Partial auto-accepts framing defaults like Full-auto (except G0/S3) while Chatterbox G1 is `automation_pending`, so the walk can advance with zero WAVs or pin the wrong producer.
- What you’d notice in Partial: Driver keeps running; G1 banner suppressed; synth/identical storms or premature_complete:vo_g1 ↔ layup (HINT VO_LADDER_PARTIAL / exec_13163).
- Why we can’t ignore it for ironclad Partial: Highest HINT family volume; without one ladder-complete law, Partial never finishes VO without intervene.
- Agent recommendation: Option **A** — one ladder-complete predicate + refuse advance past incomplete VO criticals; keep Partial framing auto-accept; never nested Partial auto-accept.
- What that recommendation gives up: Slightly slower Partial when ladder truly open; implement/test cost across pins and G1 journey.

## Context (enough to decide)
- Where in the journey (phase / stage / handoff / junction): fill_gaps (`missing_framing` / G1) → plan_rank (layup/transitions) → sound (adjudicate) → build (`vo_synthesize`); junctions `J-vo-path-ready`, `J-vo-synth-stability-g8`.
- Cousin family name (plain English): **VO ladder Partial** (`VO_LADDER_PARTIAL`).
- Glossary (only if needed):
  - **Ladder:** pickup confirmed → voice-ref approved/usable → delivery stamped → clone consent (if needed) → (synth) ≥1 synthesize line (`vo_path_ready`).
  - **Ladder-complete (proposed):** ladder + seed-complete `vo_line_adjudicate` when adjudicate enabled + G8 clear for Chatterbox batch.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Single ladder-complete SSOT; pins/G1/synth honor it; Partial keeps framing auto-accept | Error-free Partial with hosted VO | Implement cost; stricter refuse advances |
| B | Partial must-act on G-Framing / clone consent (stop auto-accept under Partial) | Human owns every VO consent | Partial no longer “accelerated” on framing |
| C | When ladder incomplete, soft-degrade to native-only (skip gap VO) and continue | Always reach master.wav | Lose synthetic framing under Partial |
| Defer | Wait for live Partial Mohan evidence on HEAD | Avoid churn if H-1 already enough | Ships with known disagree surfaces |

## Option A — Ladder-complete SSOT (recommended)
**What we would do** (plain steps, then code pointers).
1. Define `vo_ladder_complete(ctx)` (or extend `vo_path_ready`) to include: existing ladder checks; when adjudicate enabled + homunculus → `seed_stage_complete(vo_line_adjudicate)`; for Chatterbox batch → `vo_synthesize_stability_block` is None.
2. Wire refuse/advance: agenda / premature_cap / ESR VO pins / G1 synthesize-all already use pieces — make them call one helper; `vo_synthesize.require_vo_path_ready` should not Partial-stamp nested cousins (auto_accept only for Full-auto, or only for top-level synth after operator/Partial framing already stamped).
3. Keep Partial `maybe_auto_accept_gap_gate_defaults` for framing/pickup/voice-ref (current product docs) but document that G1 automation_pending ≠ ladder-complete.
4. Tests: matrix Partial + framing Yes + open consent → no synth mint; adjudicate incomplete → synth deferred; G8 layup hole → pin layup not mix.

**Pros:** Closes cousin family at root; matches Partial doctrine (auto framing, honest VO).
**Cons:** Touches guardrails + gate view + synth entry.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High |
| Cousin closure | Closes VO_LADDER_PARTIAL root |
| Complexity left | Medium (pin cousins DP-B1 still separate) |
| What you give up | Fast “fake green” G1 walks |
| Human work | Verdict only |
| Implement cost | Medium |
| Regression risk | Medium (auto_accept call sites) |
| Reversibility | High if helper feature-flagged |

**Cousin closure if chosen:** VO_LADDER_PARTIAL surfaces share one predicate.
**Tests we would add (HEAD-accurate):** Extend `test_vo_path_ready.py`, `test_hv5_*`, `test_must_precede_order.py` for ladder-complete; Partial no mid-advance past incomplete adjudicate.

## Option B — Partial must-act on framing / consent
**What we would do**
1. Gate `maybe_auto_accept_gap_gate_defaults` / `require_vo_path_ready(auto_accept=…)` so Partial never auto-stamps; journey `operator_must_act` until Yes + consent.
2. Keep Full-auto auto-accept.

**Pros:** Maximum human honesty.
**Cons:** Contradicts current Partial product copy; more operator waits.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium (honest waits, not unattended) |
| Cousin closure | Partial — still need adjudicate/G8 order |
| Complexity left | High on G8/layup |
| What you give up | Accelerated framing |
| Human work | Every Partial run acts at G-Framing |
| Implement cost | Low–medium |
| Regression risk | Low |
| Reversibility | Easy |

**Cousin closure if chosen:** Consent cousins only.
**Tests we would add (HEAD-accurate):** Partial pending framing → SystemExit / must_act; Full-auto still auto.

## Option C — Soft native-only when ladder incomplete
**What we would do**
1. If Partial and `vo_path_ready` false after N ticks → `set_gap_framing_enabled(False)` / skip gap-fill and continue ranking/mix.

**Pros:** Always progresses to master.
**Cons:** Silent quality drop; may fight operator Yes.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High for “a master exists” |
| Cousin closure | Avoids VO family by abandoning VO |
| Complexity left | Low |
| What you give up | Hosted Partial VO product |
| Human work | Low |
| Implement cost | Low |
| Regression risk | Medium (sticky No) |
| Reversibility | Medium |

**Cousin closure if chosen:** Avoidance, not closure.
**Tests we would add (HEAD-accurate):** Partial open ladder → skip path; no Chatterbox invoke.

## Option Defer — …
Wait for a clean HEAD Partial Mohan run after nested-synth tests. Risk: VO disagree remains; campaign blocked on Critical Five.

## Recommendation (not a decision)
- Preferred: Option **A**
- Why this is best for **error-free Partial**: Keeps accelerated framing; forces one completeness law before expensive synth and before claiming G1 clear.
- Honest downside: Implement surface across pins.
- Devil’s-advocate note: If Partial product intent is “Full-auto VO including auto_accept on synth,” Option A’s tighter auto_accept rules feel like a regression — say so in verdict notes.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | HINT Σ VO_LADDER_PARTIAL ≈ 747 |
| Thrash tax | Synth/adjudicate identical storms |
| Cousin surface area | Nested mint, G8, premature VO_G1, hollow adjudicate |
| Benefit under Partial | Unattended VO close |
| Replaceability | No — VO is product |

## Evidence appendix
- HEAD code + live behavior (**SSOT / evidence**): `gap_vo_gates.vo_path_ready` / `maybe_auto_accept_gap_gate_defaults` / `nested_synth_may_mint`; `stages/vo_synthesize.py` `require_vo_path_ready(..., auto_accept=True)`; `delivery_guardrails.vo_synthesize_stability_block`; `operator_gate_view.resolve_g1_vo_gate` HV-5; tests `test_vo_path_ready.py`, `test_hv5_g1_needs_operator.py`, `test_nested_synth_skip.py`.
- Docs / clinic / plans (**hints only** — verify or drop): `docs/workflows/operator-gates.md` Partial auto-accept; cousin_matrix VO_LADDER_PARTIAL; cross_surface H-1.
- Mohan HINT only: exec_13163 dominant VO_LADDER; i1/i4–i7.
- Solution-swarm raw notes: `solution_swarm/DP-VO1/` (none yet)

## Your verdict
- choice: **A+**
- notes: ladder-complete SSOT; Partial never auto_accept on synth entry; framing auto-accept kept; G1 automation_pending ≠ ladder-complete; NESTED/LAYUP/B1 separate
- date: 2026-09-21T21:35:00Z
- implemented: 2026-09-21T21:45:00Z

## YOUR NEXT ACTIONS
Closed. Paste PROGRESS_NOW from STEP_OFF.md for the next open DP.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=VO1
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
