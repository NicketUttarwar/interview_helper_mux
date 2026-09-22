# DP-BUILD-ASSEMBLY-FRESHNESS — Preview WAV is not a mix seat

- status: implemented (HAU)
- created: 2026-09-21T17:11:34Z
- implemented: 2026-09-22T01:45:00Z
- blocks: Honest music→mix→junction seating under Partial; SFX spend on preview then reseat thrash; commitment skip cousins
- resume_hook: /partial-zero-progress
- solution_swarm_agents: 1 (phase analyst / HEAD census; no product patches)
- aligns_with: DP-A5 / HX-2; family MIX_JUNCTION_SEAT; junction J-assembly-freshness

## TL;DR (read this first)
- What’s wrong (1–2 sentences): Music epoch admits on `assembly_preview.wav` **or** `assembly.wav`, but mix/junction/finalize honesty requires `mix_outputs_seated` (mtime + air-order generation + ledger commitment). Partial can burn MMAudio/palette on a preview, then thrash when mix/junction demand a real seat. A5-1 already narrowed commitment skip to **missing** assembly only — keep that; decide whether preview may admit music at all.
- What you’d notice in Partial: Music/SFX complete → mix refuses stale/unseated → junction remasters → identical seating predicates.
- Why we can’t ignore it for ironclad Partial: Wall-clock + GPU spend before a durable seat wastes Partial budgets and creates false “phase done” feelings.
- Agent recommendation: Option **A** — music requires seated mix **or** explicit Partial operator “preview music” gate; default Partial: preview for delight only, music after first seated mix (or preview+mix share clip cache SIMPLIFY).
- What that recommendation gives up: Today’s ability to generate beds before first full mix.

## Context (enough to decide)
- Where in the journey (phase / stage / handoff / junction): `assembly_preview` → music → `mix` → `junction_snip_qa`; J-assembly-freshness; Phase-A seal adjacent.
- Cousin family name (plain English): **Assembly freshness / what counts as a real mix**.
- Glossary (only if needed):
  - **Preview:** speech+VO concat, no SFX/beds — `master/assembly_preview.wav`.
  - **Seated mix:** `mix_outputs_seated` on final `master/assembly.wav`.
  - **A5-1 (HEAD):** `assert_consumer` skips generation/commitment checks only when assembly file missing.

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
| A | Music epoch requires seated `assembly.wav` (or operator preview-music gate); preview stays delight-only | Partial certainty on spend | Slower path to first beds |
| B | Keep preview admit; require reseat contract (auto remaster before mix consumers) | Keep early SFX | Still double-render; reseat bugs |
| C | SIMPLIFY: one render path — preview is a light mode of mix (shared cache) | Cut dual-audio SSOT | Larger refactor |
| Defer | Document only; soak Partial | Avoid churn | Known waste/thrash |

## Option A — Music after seated mix (recommended)
**What we would do** (plain steps, then code pointers).
1. Change `MUSIC_REQUIRES_ASSEMBLY` / `stage_outputs_present` / `delivery_stable_for_music` so preview alone does **not** admit palette/SFX/mmaudio under Partial (full-auto may keep preview admit behind config).
2. Keep `assembly_preview` + listen_delight for Phase-A seal / human listen.
3. Preserve A5-1: commitment required whenever assembly exists.
4. Tests: with only preview, music stages incomplete; with seated mix, admit.

**Pros:** Spend only on durable seat; closes freshness confuse.
**Cons:** Music later in seed; may need mix before mmaudio order rethink (today mix after mmaudio).
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High on seating |
| Cousin closure | Strong J-assembly-freshness |
| Complexity left | Seed-order: beds after mix implies order change or “beds optional until remaster” |
| What you give up | Early bed generation |
| Human work | Medium (order/policy) |
| Implement cost | Medium–high if MUST_PRECEDE flips |
| Regression risk | Medium |
| Reversibility | Config-flaggable |

**Cousin closure if chosen:** Preview≠seat; reduces mix stale after SFX.
**Tests we would add (HEAD-accurate):** music incompleteness without seated mix; Phase-A still seals on preview+delight.

**Note:** Today MUST_PRECEDE has mix after mmaudio — Option A may mean **reorder** (mix speech-only first, then music, then remaster) **or** “music assets optional until post-mix remaster.” Packet assumes operator picks sub-variant in NOTES.

## Option B — Keep preview admit + mandatory reseat
**What we would do**
1. Leave MUSIC_REQUIRES_ASSEMBLY preview OR assembly.
2. Before mix mark_done / junction commitment: always `ensure_assembly_mtime_seats_edl` + commitment verify; auto remaster if preview-era assets strapped.
3. Keep A5-1.

**Pros:** Minimal journey reorder.
**Cons:** Dual render remains; reseat thrash remains.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium |
| Cousin closure | Weak |
| Complexity left | Reseat policy |
| What you give up | Little now; pay later in thrash |
| Human work | Low |
| Implement cost | Low |
| Regression risk | Low |
| Reversibility | Easy |

**Cousin closure if chosen:** Documentation clarity mainly.
**Tests we would add (HEAD-accurate):** Preview-admit then mix seats.

## Option C — SIMPLIFY dual render into one pipeline
**What we would do**
1. `assembly_preview` becomes mix(light=True) or shared clip cache consumed by both.
2. Single freshness SSOT for “heard assembly.”
3. CUT separate preview artifact **or** make it an alias symlink to assembly when light.

**Pros:** Removes dual-SSOT class of bugs.
**Cons:** Large refactor; GUI “preview before SFX spend” UX rewrite.
**Trade-off table:**

| Axis | Assessment |
|------|------------|
| Partial certainty | High long-term |
| Cousin closure | Best structural |
| Complexity left | Low after land |
| What you give up | Short-term schedule |
| Human work | High design |
| Implement cost | High |
| Regression risk | High |
| Reversibility | Hard |

**Cousin closure if chosen:** Preview/mix dual gone.
**Tests we would add (HEAD-accurate):** One seating helper for both consumers.

## Option Defer — …
Soak Partial; treat as optimization. **Trade-off:** ironclad blocked on known waste.

## Recommendation (not a decision)
- Preferred: Option **A** (with NOTES choosing reorder vs optional-beds), or **C** if you want a CUT/SIMPLIFY investment this campaign.
- Why this is best for **error-free Partial**: Stops GPU/LLM spend on a non-seat, which is the dominant Partial economics failure in build.
- Honest downside: Forces a seed-order or “beds after first mix” product choice.
- Devil’s-advocate note: Option B is “what HEAD almost is” — if Partial soak shows rare thrash, Defer/B may be enough; HINT i11* says otherwise historically.

## Cut economics (when KEEP/SIMPLIFY/CUT is in play)
| Factor | Notes |
|--------|-------|
| Bug recurrence | HINT seating storms; dual path structural |
| Thrash tax | Full mix after full preview + SFX |
| Cousin surface area | agenda MUSIC_REQUIRES_ASSEMBLY, air_order, mix, junction |
| Benefit under Partial | High wall-clock / GPU |
| Replaceability | **SIMPLIFY/CUT** dual preview+mix (Option C); KEEP seating SSOT |

## Evidence appendix
- HEAD code + live behavior (**SSOT / evidence**):
  - `homunculus/agenda.py` `MUSIC_REQUIRES_ASSEMBLY` + `stage_outputs_present` accepts preview **or** assembly
  - `air_order.mix_outputs_seated` / `mix_stale_versus_live` / `assert_consumer` A5-1
  - `delivery_guardrails.delivery_stable_for_music` / phase_a seal
  - `stages/assembly.py` preview render vs `sound_design.mix`
- Docs / clinic / plans (**hints only**): clinic assembly_preview “Preview vs full mix dual audio SSOT”; handoff M23
- Mohan HINT only: i11 seating / stale assembly
- Solution-swarm raw notes: `solution_swarm/DP-BUILD-ASSEMBLY-FRESHNESS/`

## Named custom (operator lean) — **Heard-Assembly Unification (HAU)**

**Invoke later as:** `HAU` · `Heard-Assembly Unification` · `VERDICT=custom NOTES=HAU`

**Law (C+A federal):**
1. **C — One heard-assembly SSOT:** Preview is light/shared mode of the same seating/freshness system as mix (not a second “real show”). Music/mix/junction/finalize consult one API.
2. **A — Spend gate:** Music/SFX admit only after **seated** heard-assembly (or explicit operator `preview_music` gate). Partial never auto-opens that gate; Full-auto uses the **same** helpers (no mode carve-out that restores dual admit).
3. **Keep A5:** Commitment required whenever assembly bytes exist.
4. **Default beds policy:** `optional_beds_until_remaster` unless NOTES force seed reorder.

**In scope (fold into HAU implement):**
| Cousin | Why |
|--------|-----|
| Preview admits music (`may_admit_music` / `MUSIC_REQUIRES_ASSEMBLY`) | Core needle |
| Dual preview vs `mix_outputs_seated` freshness | Dual-SSOT root |
| Speech-first mix / music-after-seat Partial path | A spend gate |
| Agenda/runtime admit callers that still OR preview | Federal coverage |
| Light remaster after beds when preview-era assets strapped | C completeness |

**Out of scope (do not swallow — separate DPs/families):**
| Cousin | Why separate |
|--------|----------------|
| Hollow mix `mark_done` | Done Authority (closed) — only call into it |
| Wrong pin `mix_seat` / premature mix | PIN_PREMATURE (closed) |
| Junction precede / remaster_owner | Already Mix–Junction Seat Authority |
| Premix commitment diverge → incomplete_cut | Own residual; don’t redefine HAU |
| Freeze write drift (A3) | FREEZE family |
| Budget/identical thrash | BUDGET_THRASH |

**Thoroughness bar:** HAU is wide enough for the **assembly dual-SSOT** class across Partial + Full-auto. It is **not** a mega “fix all mix thrash” — cousins above stay named, not silently folded.

## Your verdict
- choice: **custom: HAU** (Heard-Assembly Unification)
- notes: Partial+Full-auto; optional_beds_until_remaster; fold dual-admit cousins only; C+A federal; Partial never auto preview-music; keep A5
- date: 2026-09-22T01:00:00Z
- implemented: 2026-09-22T01:45:00Z — `heard_assembly` + federal `may_admit_music` (seated|`preview_music`); speech-first beds all modes; `POST …/milestones/preview-music`; tests `test_hau_assembly_freshness.py`

## YOUR NEXT ACTIONS (required to progress)
HAU landed. Paste PROGRESS_NOW from STEP_OFF.md for PRE-PARTIAL.
