# Mastering construction decisions

Every compositional decision for the final master is owned by the Mastering Process and recorded in `mastering/mastering_plan.json`. No hidden hardcoded defaults downstream. Canon: [mastering-process.md](./mastering-process.md) · Engine: [mastering-shape-engine.md](./mastering-shape-engine.md).

Each decision record: `{ decision, rationale, evidence_refs[], confidence, clarifying_questions? }`.

Every decision below is additionally subject to the [quality hardening gates](./mastering-quality-hardening.md): it must be feasible, semantically non-critical, and (for clone voice) consented before it can reach the plan.

---

## Decisions → Essence mutation space

Every capability module below is a **mutator** over the Essence axes defined in [mastering-shape-engine.md § Shape as mutation engine](./mastering-shape-engine.md#shape-as-mutation-engine). Reading this table alongside that section shows which axis each decision moves:

| Capability module | Decisions owned | Essence axis mutated |
|--------------------|-----------------|------------------------|
| `cold_open_hook` | Cold open / outro kind + independent SFX switch | Synthetic inserts (+ music/SFX/air for the stinger) |
| `structure_candidates` | Overall shape, ordering/reorder/reprise, chapter boundaries, outro mirror | Native keep/order |
| `inclusion_exclusion` | Segment keep / drop / soft-focus | Native keep/order, bounded by the **hard ~10% source-runtime floor** |
| `pacing_density` | Target duration band, density, silence/transition budget | Duration (**soft ideal** vs `delivery_brief.target_duration_sec`) + air budget |
| `vo_sfx_components` | Transitions/bridges, VO bridge lines, beds/stingers/punctuators/foley | Synthetic inserts + music/SFX/air (**bed coverage 0.40–0.88**, **hinge stinger 0.3–1.0**) |

None of these mutations are free-form: they stay inside the hard invariants (pickup-preferred voice, no invented dialogue, locked speaker volleys, clone consent) and are ultimately judged by the [hard delight audit](./mastering-audition-loop.md#auditions-and-hard-delight) — a failing dimension there points back at exactly one of these rows as the axis to remutate next.

---

## Cold open / hook (`cold_open_hook`)

**Owner:** capability module `cold_open_hook` (Shape Engine schedules).  
**Plan field:** `mastering_plan.cold_open`.

| `kind` | What | Requires |
|--------|------|----------|
| `none` | Start on first ordered body segment | Always |
| `segment_hook` | Lift a high-salience source segment to the front | Real `segment_id`; Wave-3 salience; Wave-8 intelligibility |
| `vo_clone_open` | Opening line in AI clone voice (prefer pickup; any on-tape speaker with consent) | Wave-2 voice; Wave-5 synthesis; **clone consent with `cold_open` scope** |
| `vo_plus_segment` | Clone tease → segment hook | Both above |

**SFX** (independent): `{ enabled, cue_ref? }` on any non-`none` kind — opening stinger/bed from Wave-6 assets.

**Evidence to cite:** thesis/value/coherence; volleys + pickup voice; VO synthesis quality; soundscape/SFX; intelligibility/lint.

**Guards:** prefer pickup voice (any on-tape speaker OK with consent); segment_hook not duplicated later unless `reprise=true`; if nothing clears acceptance → `none` with reason.

**Realization:** first EDL element(s) — VO via pickup/synthesis path; segment cut from source; SFX via mix house chain before body.

---

## Overall shape (`structure_candidates`)

**Decision:** acts / chapters / flat / panel slots / monologue-collapse / novel layout — **or none of the above**.  
**Options:** open-ended; must be competitive and meaningfully different; cite Waves 1–8.  
**Reject:** template-only five-act, copy-paste chapter formulas without tape support.  
**Realization:** informs chapter metadata + ordering constraints in ranking/EDL; plan is authority.

---

## Segment inclusion / exclusion / focus (`inclusion_exclusion`)

**Decision:** which segments keep / drop / soft-focus.  
**Acceptance:** every exclude has rationale; locked speaker volleys intact; prefer clarity over keeping everything.  
**Realization:** binds `selection.ordered_segment_ids` / excludes; creative_delivery must not fight plan without plan-level override.

---

## Segment ordering / reorder / reprise

**Owners:** `structure_candidates` + `inclusion_exclusion`.  
**Decision:** body order; optional reprise of hook segment (flagged).  
**Realization:** EDL speech order.

---

## Chapter / section boundaries + titles (`structure_candidates`)

**Decision:** optional chapters with titles and open segment ids.  
**Acceptance:** titles grounded in dossier; no empty padding acts.  
**Realization:** narrative/EDL chapter cues when present.

---

## Transitions / spoken bridges (`vo_sfx_components`)

**Evidence:** Wave-3 `transition_bridge_inventory`.  
**Decision:** which bridges to write/keep/drop.  
**Realization:** `transitions` stage + EDL transition clips bound to plan.

---

## VO bridge lines — pickup voice (`vo_sfx_components`)

**Evidence:** Wave-5.  
**Decision:** which gap/framing/reaction lines to include; voice must be pickup-eligible.  
**Realization:** `vo_pickup/` + EDL VO placement; synthesis ladder when plan chooses clone.

---

## Beds / stingers / punctuators / foley (`vo_sfx_components`)

**Evidence:** Wave-6.  
**Decision:** include/exclude + placement intent; reject wallpaper / repetitive gestures.  
**Realization:** SDP + MMAudio + mix overlays; plan gates density.

---

## Pacing / duration / density / silence (`pacing_density`)

**Decision:** target duration band, segment density, silence/transition budget.  
**Acceptance:** fits source length realism; no empty padding; no repetitive energy pattern.  
**Realization:** delivery-brief soft targets become plan-bound; ranking/trim follow plan.

---

## Outro / payoff / close (`structure_candidates` + episode_close)

**Spoken** outro / payoff VO remains dynamically chosen (`none` | `segment` | `vo` | `vo+sfx`) and is not required.

**Musical episode close is required:** `mastering_plan.episode_close.music` always requests `theme_outro` after the last native with a gentle long fade. See [information-packages.md](./information-packages.md). Realization: SDP seed + mix bookend fade (`bookend_fade_out_ms`).

---

## Information packages (mid-episode)

**Owner:** delivery stage `information_package_plan` (Shape-owned plan field).  
**Plan field:** `mastering_plan.information_packages` (0–2).  
High-bar music face-out (`theme_chapter_resolve`) + dense Nugget Layup before-VO. Not a cold open. Details: [information-packages.md](./information-packages.md).

---

## Ducking / spatial pan / level tiers

**Owner:** Realization mix, bounded by plan intent.  
**Evolve:** `tbiy_mix.py` → mastering mix helpers (pan, bed/foley under dialogue, duck under speaker volleys).  
**Plan may set:** intent flags / target tiers; not sample-accurate automation.

---

## Loudness / final QC

**Owner:** Realization (`master_finalize`, `verify_master`).  
**Plan may set:** target LUFS intent (default −16 podcast).  
**Hard:** verify_master remains mechanical gate.

---

## Ensemble rule

Cold open + body + VO/SFX + close must read as **one bespoke solution**. L4 and flagship synthesize reject mismatched or programmatic ensembles even if each piece is locally “valid.”


## Narrative mode + montage grammar (`structure_candidates` / L0)

**Owner:** Shape L0 + structure/vo modules (two-pass).  
**Plan fields:** `narrative_mode`, `montage_grammar`, `listener_outcome`, `pass`, `plan_status`.

See [narrative-mode-and-montage.md](./narrative-mode-and-montage.md). Prefer/forbid: [narrative-mode-prefer-forbid.json](./narrative-mode-prefer-forbid.json).

**Sonic density** by mode binds SDP/MMAudio when `consumers_bind` is true.

