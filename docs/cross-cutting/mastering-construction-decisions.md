# Mastering construction decisions

Every compositional decision for the final master is owned by the Mastering Process and recorded in `mastering/mastering_plan.json`. No hidden hardcoded defaults downstream. Canon: [mastering-process.md](./mastering-process.md) · Engine: [mastering-shape-engine.md](./mastering-shape-engine.md).

Each decision record: `{ decision, rationale, evidence_refs[], confidence, clarifying_questions? }`.

Every decision below is additionally subject to the [quality hardening gates](./mastering-quality-hardening.md): it must be feasible, semantically non-critical, and (for clone voice) consented before it can reach the plan.

---

## Cold open / hook (`cold_open_hook`)

**Owner:** capability module `cold_open_hook` (Shape Engine schedules).  
**Plan field:** `mastering_plan.cold_open`.

| `kind` | What | Requires |
|--------|------|----------|
| `none` | Start on first ordered body segment | Always |
| `segment_hook` | Lift a high-salience source segment to the front | Real `segment_id`; Wave-3 salience; Wave-8 intelligibility |
| `vo_clone_open` | Opening line in **pickup-eligible** AI clone voice | Wave-2 pickup voice; Wave-5 synthesis ladder; **clone consent with `cold_open` scope**; never guest voice |
| `vo_plus_segment` | Clone tease → segment hook | Both above |

**SFX** (independent): `{ enabled, cue_ref? }` on any non-`none` kind — opening stinger/bed from Wave-6 assets.

**Evidence to cite:** thesis/value/coherence; volleys + pickup voice; VO synthesis quality; soundscape/SFX; intelligibility/lint.

**Guards:** pickup-voice invariant; segment_hook not duplicated later unless `reprise=true`; if nothing clears acceptance → `none` with reason.

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

## Outro / payoff / close (`structure_candidates`)

Mirror of cold-open logic: `none` | `segment` | `vo` | `vo+sfx` — dynamically chosen, not required.  
**Realization:** trailing EDL element(s).

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
