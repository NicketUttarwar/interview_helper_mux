# DP-NESTED-SYNTH — Nested EDL/transition Chatterbox vs VO ladder

- status: closed
- created: 2026-09-21T17:15:00Z
- closed: 2026-09-21T22:25:00Z
- blocks: (resolved) nested mint skip-not-stamp A
- resume_hook: (closed — see decision_log)

## TL;DR (read this first)
- What’s wrong (1–2 sentences): Nested Chatterbox from EDL/transition resync historically could mint or auto-accept gates while the VO ladder was open. HEAD already has `nested_synth_may_mint` (Partial never auto-accept; skip-not-stamp) and cascade tests — but clinic/cross_surface still flagged H-1 open, `vo_synthesize` still calls `require_vo_path_ready(..., auto_accept=True)`, and exception fail-open paths can drop the gate.
- What you’d notice in Partial: EDL/transitions “succeed” with `nested_synth_skipped:vo_path_not_ready:*` notes and no new WAVs; later synth/G1 must own demand — or, if a path still mint/stamps, Partial lies.
- Why we can’t ignore it for ironclad Partial: Nested mint is the classic Partial footgun (stamp consent from EDL). Need an explicit KEEP vs tighten vs soften verdict.
- Agent recommendation: Option **A** — KEEP skip-not-stamp; close remaining fail-open/except paths; Partial never auto_accept on nested **or** top-level require when called from nested context; WAV demand → G1 / `vo_synthesize` / mix incompleteness.
- What that recommendation gives up: EDL may complete “without audio” until later stages; wall-clock longer.

## Context (enough to decide)
- Where in the journey (phase / stage / handoff / junction): plan_rank `transitions` artifacts consumed in build `edl` / `vo_synthesize`; fill_gaps ladder readiness. Junction `J-nested-synth-mint`.
- Cousin family name (plain English): **Nested synth vs VO ladder** (H-1 / VO_LADDER cousin).
- Glossary (only if needed):
  - **Nested mint:** Chatterbox/S2S invoked from EDL or transition resync, not from `vo_synthesize` stage ownership.
  - **Skip-not-stamp:** Log skip note, continue stage, do not `maybe_auto_accept` under Partial.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | KEEP skip-not-stamp; seal fail-open holes; no Partial nested auto_accept | Matches decided H-1; Partial honesty | EDL green without WAVs until synth |
| B | Soft-block EDL/transitions until ladder ready | No silent skip | Partial stalls mid-plan_rank/build |
| C | Allow Partial nested auto_accept (Full-auto parity) | Faster local WAV fill | Reopens gate-stamp footgun |
| Defer | Treat HEAD tests as done; no further work | Save cycles | Ambiguous campaign status on H-1 |

## Option A — KEEP skip-not-stamp + seal holes (recommended)
**What we would do** (plain steps, then code pointers).
1. Affirm current `nested_synth_may_mint` behavior as Partial law.
2. Harden callers: `resync_required_synthesize_wavs`, `resync_spoken_transitions` — on exception around readiness, **fail closed to skip** (not mint); never swallow into synth.
3. Ensure nested entry never calls `require_vo_path_ready(auto_accept=True)` under Partial; top-level `vo_synthesize` auto_accept policy owned by DP-VO1.
4. Tests: keep/extend `test_nested_synth_skip.py`; add except-path does not mint; Full-auto may still auto_accept then mint.

**Pros:** Aligns with operator-decided cross_surface H-1; low product risk.
**Cons:** Relies on DP-VO1 so skipped WAVs still close later.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High if VO1 lands |
| Cousin closure | Closes nested stamp/mint cousins |
| Complexity left | Low |
| What you give up | Immediate WAV at EDL |
| Human work | Verdict |
| Implement cost | Low (seal holes) |
| Regression risk | Low |
| Reversibility | High |

**Cousin closure if chosen:** Nested mint family.
**Tests we would add (HEAD-accurate):** Exception path skip; Partial zero new clone WAVs + note; Full-auto mint when ready.

## Option B — Soft-block until ladder ready
**What we would do**
1. When `nested_synth_may_mint` false → incompleteness / defer EDL (or transitions) to `missing_framing` / ladder pin instead of skip-continue.

**Pros:** No wavs=0 after “successful” EDL.
**Cons:** Partial can stick on EDL while framing automation_pending; fights H-1 “don’t hard-stop EDL.”
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium (honest stall) |
| Cousin closure | Different shape |
| Complexity left | Pin storms |
| What you give up | H-1 continue semantics |
| Human work | Medium |
| Implement cost | Medium |
| Regression risk | Medium |
| Reversibility | Medium |

**Cousin closure if chosen:** Forces ladder before EDL.
**Tests we would add (HEAD-accurate):** Partial open ladder → edl deferred/incomplete not skip note.

## Option C — Partial nested auto_accept
**What we would do**
1. Treat Partial like Full-auto inside `nested_synth_may_mint` (`auto_accept=True`).

**Pros:** More WAVs earlier.
**Cons:** Explicitly undoes H-1 / Partial consent honesty.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low for consent honesty |
| Cousin closure | Reopens stamp cousins |
| Complexity left | High ethics debt |
| What you give up | Operator gate meaning |
| Human work | Low |
| Implement cost | Trivial |
| Regression risk | High (policy) |
| Reversibility | Easy |

**Cousin closure if chosen:** None — regresses.
**Tests we would add (HEAD-accurate):** Would need to rewrite nested skip tests — red flag.

## Option Defer — …
Close H-1 as “already implemented” with no packet work. Risk: `vo_synthesize` auto_accept + except fail-open remain undocumented for Partial Zero.

## Recommendation (not a decision)
- Preferred: Option **A**
- Why this is best for **error-free Partial**: Matches decided skip-not-stamp; cheapest honesty win; pairs with DP-VO1 for reclaim.
- Honest downside: EDL “success” without audio looks weird until synth.
- Devil’s-advocate note: If live Partial still mints under skip notes, Option A implement step 2 is mandatory — not optional polish.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | H-1 P0 in cross_surface; tests already assert skip |
| Thrash tax | Wrong mint → WAV purge/reburn |
| Cousin surface area | Nested + top-level auto_accept |
| Benefit under Partial | Consent honesty |
| Replaceability | Nested path is convenience; VO stage is owner |

## Evidence appendix
- HEAD code + live behavior (**SSOT / evidence**): `gap_vo_gates.nested_synth_may_mint`; `stages/assembly.py` resync skip return; `transition_vo.py` resync skip; `tests/test_nested_synth_skip.py` PASS intent.
- Docs / clinic / plans (**hints only**): `.cursor/plans/cross_surface_gaps_report.md` H-1 decided skip-not-stamp but row still “open”; clinic full_auto_readiness nested line.
- Mohan HINT only: VO_LADDER_PARTIAL volume includes synth-before-ready shapes.
- Solution-swarm raw notes: `solution_swarm/DP-NESTED-SYNTH/` (none yet)

## Your verdict
- choice: **A**
- notes: KEEP skip-not-stamp; seal probe fail-open on resync callers; residuals 1–3 (framing detect fail-closed, framing Yes gates before delivery stamp, vo_bind/host mint SSOT)
- date: 2026-09-21T22:20:00Z
- implemented: 2026-09-21T22:25:00Z
- residuals_1_3: 2026-09-21T22:55:00Z

## YOUR NEXT ACTIONS
Closed. Paste PROGRESS_NOW from STEP_OFF.md.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=NESTED-SYNTH
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
