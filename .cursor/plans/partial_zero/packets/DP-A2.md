# DP-A2 — Two freeze constitutions (End-A vs ship-omit vs packaging)

- status: implemented
- created: 2026-09-21T17:15:00Z
- decided: 2026-09-21T17:26:00Z
- implemented: 2026-09-21T17:31:45Z
- blocks: FREEZE_CONSTITUTION family; junction omit under freeze; CTA/sanitize policy; Partial unattended heal after hard freeze
- resume_hook: (done — next DP-A1)

## TL;DR (read this first)
- What’s wrong (1–2 sentences): Paper says **End-A allowlist only**. HEAD still has **three** proceed paths under freeze: End-A in `seat_authority.py`, **ship-blocking omit** in `air_order_boundary._ship_blocking_omit_ids`, and **packaging/catastrophe** substring escapes in `seat_mutation_allowed`.
- What you’d notice in Partial: Either freeze restores omitted ids → mix `incomplete_cut_unresolved` forever, or silent packaging bypasses that never hit End-A.
- Why we can’t ignore it for ironclad Partial: Freeze is the seat constitution; dual lists mean Partial cannot predict refuse vs land without forensics.
- Agent recommendation: Option **A** — **named End-A allowlist** for today’s ship-blocking omit/integrity actions; delete packaging substring auto-allow (CTA named or meta-gate).
- What that recommendation gives up: Substring convenience; every new repair must earn an allowlist row.

## Context (enough to decide)
- Where in the journey: Post–VO hard freeze; junction ladder omit/fuse; overlap-union; CTA/sanitize; synth-fail unseat.
- Cousin family name: **FREEZE_CONSTITUTION** (`J-freeze-constitution`).
- Glossary:
  - **End-A:** `HARD_FREEZE_ALLOWLIST_ACTIONS` — paperwork/shrink/orientation only today.
  - **Ship-blocking omit:** omit-only deltas with `junction_snip_qa:` + incomplete-cut kinds, or producers `edl_overlap_repair` / `segment_id_remap` — locked by i30/i37 tests; **not** on End-A list.
  - **Packaging escape:** reason substrings `media_ip_cta`, `cta_omit`, … bypass rewrite budget.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | One End-A list: register ship-repair omit/integrity as **named** actions; kill packaging substring | Single constitution + Partial can still heal ship-blocks | Explicit allowlist growth |
| B | End-A only; **refuse** ship-blocking omits until operator unlock | Literal “allowlist only, no carve-outs” | Reopens incomplete_cut deadlock class |
| C | Keep dual constitution; document omit as sole second list; freeze packaging separately | Minimal code churn | Two modules forever |
| Defer | Wait for live freeze+omit Partial | Avoid policy fight | Unattended freeze undefined |

## Option A — Named End-A allowlist (recommended)
**What we would do**
1. Add named actions for today’s ship-blocking kinds (e.g. `junction_incomplete_cut_omit`, `edl_overlap_repair_omit`, `segment_id_remap_omit`) to `HARD_FREEZE_ALLOWLIST_ACTIONS`.
2. Route `_ship_blocking_omit_ids` / `commit_selection_mutation` through `hard_freeze_action_permitted` (or delete parallel list and call End-A only).
3. Delete packaging substring auto-allow; CTA either named End-A rows or always meta-gate.
4. Keep i30/i37 green by mapping to named rows (not a second constitution).
**Pros:** One list operators can audit; Partial heals ship-blocks without unlock; packaging honesty.
**Cons:** Allowlist becomes the product surface; every new repair needs a row.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High — predictable freeze |
| Cousin closure | Closes dual-list FREEZE cousins; packaging substring CUT |
| Complexity left | Medium allowlist stewardship |
| What you give up | Substring convenience; silent packaging |
| Human work | Verdict on each named row |
| Implement cost | Medium (seat_authority + boundary + tests) |
| Regression risk | Medium (must not drop i30/i37) |
| Reversibility | High if rows feature-flagged |

**Cousin closure if chosen:** FREEZE_CONSTITUTION root; feeds A3 writer gates.
**Tests:** `test_enda_hard_freeze_constitution.py` requires ship-repair kinds on allowlist; packaging substring must refuse; keep `test_i29_junction_ladder_can_land_omit.py`.

## Option B — End-A only; refuse ship-blocking omits
**What we would do:** Freeze restores omitted ids (or refuse commit). Mix/PMQ stay red until operator unlock. Delete or ignore `_ship_blocking_omit_ids` proceed path. Matches mechanism honesty **Decision A2-2**.
**Pros:** Narrowest allowlist; no “hidden” second module.
**Cons:** Reopens exec_11871 deadlock — Partial **cannot** clear incomplete_cut without human; fails “Partial without forensics.”
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low for unattended Partial — deadlocks |
| Cousin closure | Honesty of allowlist; opens ship-block cousin |
| Complexity left | Low code; high ops tax |
| What you give up | Unattended junction heal under freeze |
| Human work | Unlock every stuck omit |
| Implement cost | Low–medium (delete carve-out + update i30/i37) |
| Regression risk | High (known deadlock class) |
| Reversibility | Medium |

**Cousin closure if chosen:** Dual-list closed by amputation; MIX incomplete_cut cousin reopens.
**Tests:** Expect omit refused; mix red — not Partial-friendly.

## Option C — Keep dual constitution (document only)
**What we would do:** Leave End-A + `_ship_blocking_omit_ids` + packaging/catastrophe. Document ship-blocking omit as the only intentional second list; treat packaging as soft-budget escape.
**Pros:** Zero behavior change; i30/i37 stay.
**Cons:** Operators still cannot reason from one file; packaging substring remains a hole.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium-low — law stays split |
| Cousin closure | None at root |
| Complexity left | High (two modules + substrings) |
| What you give up | Constitutional honesty |
| Human work | Docs only |
| Implement cost | Near zero |
| Regression risk | Low short-term |
| Reversibility | N/A |

**Cousin closure if chosen:** Does not close FREEZE_CONSTITUTION.
**Tests:** Doc/assert dual paths exist (weak).

## Option Defer — Live freeze evidence first
**What we would do:** Reopen after Partial shows restore-vs-omit fingerprint.
**Pros:** Avoid wrong policy.
**Cons:** Campaign already knows the split from HEAD.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Low |
| Cousin closure | None |
| Complexity left | Unchanged |
| What you give up | Policy clarity now |
| Human work | Watch |
| Implement cost | Zero |
| Regression risk | Zero |
| Reversibility | N/A |

## Recommendation (not a decision)
- Preferred: Option **A**
- Why this is best for **error-free Partial**: Keeps ship-blocking repairs legal **as named End-A rows** (no second constitution) so junction can land omits under freeze without operator unlock — unlike B, which re-deadlocks mix. Cuts packaging substring lies.
- Honest downside: Allowlist grows; reviewers must gate new actions.
- Devil’s-advocate note: Mechanism honesty **Decision A2-2** (refuse omits) is cleaner paper — but it trades Partial zero for operator unlocks. Campaign law prefers A.

## Cut economics (KEEP / SIMPLIFY / CUT) — strong pass
| Factor | Option A (named End-A) | Option B (refuse omit) | Option C (dual) |
|--------|------------------------|------------------------|-----------------|
| Bug recurrence | Low if rows explicit | High incomplete_cut restore loops | Medium silent drift |
| Thrash tax | Low (omit lands) | Very high (mix forever red) | Medium packaging thrash |
| Cousin surface area | One module | One module + unlock UX | Two modules forever |
| Benefit under Partial | Heal without forensics | Honesty only with humans | Status quo |
| Replaceability | CUT parallel list; KEEP named repairs | CUT ship-repair ability | KEEP everything |
| Cut verdict | **KEEP repairs as named rows; CUT substring packaging; CUT second module** | **CUT ship-repair under freeze** (expensive) | **KEEP dual** (no cut) |

| Ledger row | Notes |
|------------|-------|
| Bug recurrence | Dual list → restore-omit ping-pong (HINT exec_11871 / i30 class) |
| Thrash tax | Mix incomplete_cut × N until halt |
| Cousin surface area | seat_authority + air_order_boundary + packaging tokens |
| Benefit under Partial | Single audited End-A file |
| Replaceability | Ship-omit logic maps 1:1 to named actions — do not CUT capability, CUT the second constitution |

## Evidence appendix
- HEAD code + live behavior (**SSOT / evidence**):
  - `src/interview_mux/seat_authority.py` `HARD_FREEZE_ALLOWLIST_ACTIONS`, `hard_freeze_action_permitted`, `seat_mutation_allowed` (packaging/catastrophe)
  - `src/interview_mux/air_order_boundary.py` `_ship_blocking_omit_ids`, `commit_selection_mutation` honor path
  - Tests: `tests/test_enda_hard_freeze_constitution.py`, `tests/test_i29_junction_ladder_can_land_omit.py`, `tests/test_seat_pin_constitution.py`
- Docs / clinic / plans (**hints**): `mechanism_honesty_breakpoints.md` BP-A2; `cross_surface_gaps_report.md` G-4/H-3; `cousin_matrix.md` FREEZE_CONSTITUTION
- Mohan HINT only: i30/i37 class — verify HEAD tests
- Solution-swarm raw notes: `solution_swarm/DP-A2/`

## Your verdict
- choice: A
- notes: named End-A allowlist; cut packaging substring
- date: 2026-09-21T17:26:00Z

## YOUR NEXT ACTIONS (required to progress)
DP-A2 is **implemented** (named End-A; packaging substring CUT). Next: present/answer **DP-A1**.
1. Paste PROGRESS_NOW from STEP_OFF.md into Agent.
2. Or answer: `/partial-zero-answer DP=A1 VERDICT=… NOTES=…`

## COPY-PASTE INTO CURSOR AGENT

### PROGRESS_NOW
(see STEP_OFF.md — always the live next-step command)

### DIG_DEEPER
```
/partial-zero-explain-simple DP=A2
Explain End-A named allowlist vs refuse ship-omit vs dual constitution for Partial zero. No product patches.
```
