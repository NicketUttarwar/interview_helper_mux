# DP-BUILD-HOLLOW-MIX — Mix says it refused done, then still tries to stamp

- status: awaiting_operator
- created: 2026-09-21T17:11:34Z
- blocks: Honest mix completion under Partial; AuthorityDenied / silent no-stamp after successful render; remaster inherit hollow deny
- resume_hook: /partial-zero-answer DP=BUILD-HOLLOW-MIX VERDICT=…
- solution_swarm_agents: 1 (phase analyst / HEAD audit; no product patches)
- aligns_with: DP-B4 (mark_done honesty); family HOLLOW_DONE; junction J-hollow-done

## TL;DR (read this first)
- What’s wrong (1–2 sentences): After mix render, code logs “outputs not fully seated — refuse mark_done” then **unconditionally** calls `ctx.mark_done("mix")`. If the seating `try` raises, the refuse check is skipped entirely. Ownership/`FORCE_DONE_GUARDED` usually blocks a hollow stamp, but callers still see a confusing success path / raised AuthorityDenied after a good WAV.
- What you’d notice in Partial: Mix rendered `assembly.wav` then `authority_denied:mark_done:hollow:mix` or silent no `.stage_done`; junction remaster hits the same hollow; A1-1 then keeps junction first.
- Why we can’t ignore it for ironclad Partial: Build “done” must mean seated mix, not “render happened.”
- Agent recommendation: Option **A** — hard gate: if not `mix_outputs_seated` after seat attempt, **do not call** `mark_done`; raise loud classified incompleteness (or heal-then-retry once).
- What that recommendation gives up: Soft “log and let mark_done decide” indirection.

## Context (enough to decide)
- Where in the journey (phase / stage / handoff / junction): `build` / `sound_design.mix` exit; J-hollow-done; feeds J-mix-junction-precede.
- Cousin family name (plain English): **Hollow done / false complete**.
- Glossary (only if needed):
  - **`mix_outputs_seated`:** mtime fresh vs EDL + live gen + ledger commitment (not preview).
  - **`ensure_assembly_mtime_seats_edl`:** bumps assembly mtime after EDL skew (HX-2 / i11).

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | After seat attempt: if not seated → raise / return before mark_done; never log-lie | Ironclad honesty | Mix stage fails louder after render |
| B | Keep call mark_done but make mark_done always raise (never silent return) on mix incompleteness | One choke point | Broader mark_done behavior change (DP-B4) |
| C | On unseated: auto heal seat (mtime+ledger rewrite) then mark_done once; else raise | Fewer operator interventions | Risk greenwashing bad commitment |
| Defer | Rely on ownership refuse + i11 tests | Avoid churn | Log-lie + except-skip remain |

## Option A — Refuse before mark_done (recommended)
**What we would do** (plain steps, then code pointers).
1. In `sound_design.mix` after `ensure_assembly_mtime_seats_edl`: if not `mix_outputs_seated`, **raise** classified error (or return without mark_done) — do not call `mark_done`.
2. Do not wrap seating in fail-open `except` that skips the gate; log then re-raise or treat as unseated.
3. Remaster path already reseats mtime after promote — keep that; assert seated before any junction claims mix done.
4. Tests: unseated after render never creates `.stage_done/mix`; seating exception does not stamp.

**Pros:** Local honesty; small blast radius; matches log text.
**Cons:** More loud fails until seating bugs fixed.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High for mix stamp |
| Cousin closure | Closes mix hollow surface; DP-B4 still open elsewhere |
| Complexity left | Low |
| What you give up | Soft fall-through to mark_done |
| Human work | Low |
| Implement cost | Low |
| Regression risk | Low–medium |
| Reversibility | Easy |

**Cousin closure if chosen:** Mix hollow stamp path; couples with DP-BUILD-MIX-JUNCTION (unmarked mix trap).
**Tests we would add (HEAD-accurate):** Extend `test_i11_mix_mark_done_seats_mtime.py` — assert no marker when unseated; exception path.

## Option B — mark_done always loud for mix
**What we would do**
1. In `run_context.mark_done`, for `FORCE_DONE_GUARDED` incompleteness: **raise** instead of log+return (at least for `mix` / junction).
2. Leave mix body as-is (still calls mark_done).

**Pros:** Fixes silent no-stamp cousins for all guarded stages.
**Cons:** Cross-cutting DP-B4 decision; more stages start raising mid-walk.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium–high |
| Cousin closure | Better family-level (HOLLOW_DONE) |
| Complexity left | Caller catch sites |
| What you give up | Soft refuse semantics |
| Human work | Medium (B4 scope) |
| Implement cost | Medium |
| Regression risk | Medium |
| Reversibility | Medium |

**Cousin closure if chosen:** Stronger HOLLOW_DONE; still leaves misleading mix log.
**Tests we would add (HEAD-accurate):** mark_done raises on mix unseated; callers expect raise.

## Option C — Auto-heal seat then stamp
**What we would do**
1. If not seated: rewrite ledger fingerprint / bump mtime / `stamp_after_mix` again; retry `mix_outputs_seated`.
2. If still false: raise.

**Pros:** Tolerates HX-2 skew without failing the stage.
**Cons:** Can stamp when commitment still diverges if heal is mtime-only.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium — depends on heal completeness |
| Cousin closure | Weak if heal incomplete |
| Complexity left | Heal policy |
| What you give up | Fail-loud seating bugs |
| Human work | Medium |
| Implement cost | Medium |
| Regression risk | Higher |
| Reversibility | Medium |

**Cousin closure if chosen:** Skew cousin only.
**Tests we would add (HEAD-accurate):** Skew auto-heals; commitment mismatch still refuses.

## Option Defer — …
**What we would do:** Keep i11 mtime seat + ownership raise.
**Pros:** Already partially fixed.
**Cons:** Log-lie + except-skip remain Partial hazards.
**Trade-off table:** certainty low · cousins open · cost zero.

## Recommendation (not a decision)
- Preferred: Option **A**
- Why this is best for **error-free Partial**: Makes the mix exit match the log and seating SSOT without widening mark_done yet (B can follow as DP-B4).
- Honest downside: More visible mix failures until seating is reliable.
- Devil’s-advocate note: Option C is tempting because i11 was “just mtime skew” — but commitment SHA mismatch must stay fail-closed.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | HINT HOLLOW_DONE 48 on exec_13167 alone |
| Thrash tax | Remaster + junction inherit hollow |
| Cousin surface area | mark_done, ownership, mix, remaster |
| Benefit under Partial | High |
| Replaceability | KEEP mix; SIMPLIFY stamp path |

## Evidence appendix
- HEAD code + live behavior (**SSOT / evidence**):
  - `sound_design.py` mix exit ~1240–1258: log refuse → still `mark_done("mix")`; seating in try/except
  - `run_context.mark_done`: AuthorityDenied raises; incompleteness often log+return
  - `artifact_ownership.assert_may_mark_done` → `stage_outputs_present` → `mix_outputs_seated`
  - `stage_completion._mix_unseated_incompleteness`
  - `tests/test_i11_mix_mark_done_seats_mtime.py`
- Docs / clinic / plans (**hints only**): mechanism BP-B4; clinic mix map hollow mtime
- Mohan HINT only: i11 / i11h hollow mark_done
- Solution-swarm raw notes: `solution_swarm/DP-BUILD-HOLLOW-MIX/`

## Your verdict
- choice: A | B | C | … | Defer | custom: …
- notes:
- date:

## YOUR NEXT ACTIONS (required to progress)
This DP is PAUSED until you answer.
1. Optional: Ask mode or paste DIG_DEEPER into Agent.
2. To decide: `/partial-zero-answer DP=BUILD-HOLLOW-MIX VERDICT=… NOTES=…`
3. To advance after that: paste PROGRESS_NOW from STEP_OFF.md into Agent.

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=BUILD-HOLLOW-MIX
Explain options and trade-offs for Partial zero in plain language. No product patches.
```
