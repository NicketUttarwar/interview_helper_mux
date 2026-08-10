# Mastering Process (canonical)

> **One interview → one bespoke `master/master.wav`.** Structure emerges from source + assets + operator intent — never from a fixed template.

**TBIY heritage:** [tbiy-production-profile.md](./tbiy-production-profile.md) was the original Wondery-style compass. The Mastering Process **evolves past TBIY**. Five-act / moat / dual-voice are optional tools when evidence supports them — not an enforced compass. Useful TBIY discipline retained: **prefer pickup-eligible (least-spoken) voice for new VO** (any on-tape speaker allowed with consent when needed); never invent unspoken dialogue; speech-wins ducking under speaker volleys.

**Reliability layer:** [mastering-quality-hardening.md](./mastering-quality-hardening.md) — routing, evidence packets, diversity, feasibility, semantic integrity, clone consent, auditions, multi-critic L4, Pareto, closed-loop polish. Shape hardening gates remain soft by default; **listen delight is an authoritative ship gate** (see [NORTH_STAR.md](../../NORTH_STAR.md)).

**Narrative excellence:** [narrative-mode-and-montage.md](./narrative-mode-and-montage.md) — two-pass Shape (`narrative_mode` + `montage_grammar`), 8-wave research dossier. Listen delight is **authoritative** for ship (finalize quality + publish).

**Related:** [mastering-research-fields.md](./mastering-research-fields.md) · [mastering-shape-engine.md](./mastering-shape-engine.md) · [mastering-construction-decisions.md](./mastering-construction-decisions.md) · [mastering-integration-backlog.md](./mastering-integration-backlog.md) · [mix-house-chain.md](./mix-house-chain.md) · [volley-glossary.md](./volley-glossary.md)

---

## Macro shape

```
Research lane (8 waves / 38 fields, dynamically routed)
  → Shape Composition Engine (L0–L5 + capability modules + hardening gates + flagship synthesize)
  → Realization & Polish (audio-grounded, bounded remux)
  → master/master.wav (−16 LUFS)
```

| Lane | Authority | Output |
|------|-----------|--------|
| Research | Descriptive dossier only | `mastering/research_dossier.json` |
| Shape Engine | **Sole intent** for construction | `mastering/mastering_plan.json` |
| Realization | Execute plan → audio | EDL → mix → `master/master.wav` |

**Principle:** No five-act, cold-open→payoff, or documentary checklist is enforced. Each podcast gets a **custom** analysis agenda and a **bespoke** component ensemble.

---

## North-star (every Shape Engine level)

> Produce the **absolute best** final podcast construction for *this* tape — the most impressive, compelling, information-rich listen — as a **bespoke** combination of **native nuggets + grounded synthetic conversation + musical/sonic scenes**, not a programmatic template.

**Essence (structure-first):** Prefer golden nuggets over padded tape; cut for idea impact and listenability; weave native ↔ synthetic ↔ music/SFX/air as one conversation; mutate keep/order/bridges/beds toward the most information in the best manner. Soft duration ideal; hard floor ~10% of source only. Bed coverage **0.28–0.88**, hinge stinger **0.3–1.0** (Shape-owned soft bands).

**Talking-points-first cuts (analysis):** After `content_context`, `talking_points_compose` → `ideal_cuts_propose` → `ideal_cuts_materialize` choose holistic talking points and snap ideal native windows to word timestamps. With `analysis.ideal_cuts.bind_mode=both` (default), materialize publishes `segments/boundaries.json` (skipping the boundary LLM when valid), skips topic resplit + classification LLM when bound, and seeds ranking order. Coverage + narrative + classification are synthesized deterministically when `analysis.talking_points_authority.*` is on (LLM fallback otherwise). See `analysis.ideal_cuts.*` in [config-keys.md](./config-keys.md).

**Nugget Layup System (synthetic VO):** After selection freezes, flagship `nugget_corpus_mine` + `nugget_layup_compose` assess the **full transcript** (including excluded natives) and write a relevant before-VO lay-up for each kept segment so discarded facts still reach the listener. Canon: [nugget-layup-system.md](./nugget-layup-system.md).

**Slim delivery Pass-2:** Only `refinement_agenda` → `gap_framing_recompose` → `selection_framing_apply` remain in `DELIVERY_ORDER` after layups. When layups own `gap_report`, recompose is a thin adapter. Early `sound_design_palettes` LLM is off by default (`sound_design.early_palettes_llm=false`); SDP owns musical direction. Prompts are unified (no TBIY dual path).

**Slim Shape soft-gate:** Default `mastering.shape.soft_gate.max_mode_candidates=2` with `skip_diversity=true`. Full L0–L5 / capability-module docs describe the aspirational mutation engine; the shipped runtime is the two-pass soft-gate compiler in `mastering_shape_runtime.py`.

**System-instruction pillars** (every minted/edited shape prompt; L4 especially):

1. Best final outcome for the listener
2. Promote excellence (unequal options)
3. Filter ruthlessly (kill dull / generic / padded) — keep golden nuggets
4. Bespoke, not programmatic
5. Non-repetitive
6. Best *ensemble* (cold open + body + VO/SFX + close) — native proof + grounded synthetic + sonic weave
7. Convey real knowledge (no invented unspoken dialogue)
8. Impressive when earned (restraint otherwise)
9. **Worth finishing / lovable** — finishability and recommendability are **hard ship criteria** via authoritative listen_delight (equal class to verify_master / scorecard)

---

## Cross-cutting loops

### Prompt mint (+ Shape Engine edit)

1. **Mint** (economy/standard) → `mastering/prompts_minted/{id}.vN.system.txt` or envelope JSON
2. **Run** multi-turn LLM volley (system → user → assistant → …)
3. **Acceptance** gate (completeness, evidence, confidence)
4. **Clarify** if ambiguous — auto-resolve from artifacts first; else operator GUI (capped; timeout → `assumption` records)
5. **Shape only — Prompt edit:** if framing was checklist-y / not excellence-seeking → rewrite `vN+1`, log in `prompt_edit_log`, re-run

### Skip / absent-aware

If the operator skipped a flow (no G1 VO, no preclean, no NLE), the field reports `status=skipped_or_thin` — never invent evidence.

### Model tiers

| Role | Tier |
|------|------|
| Prompt mint / edit / acceptance / clarify triage / research fields | economy or standard |
| Shape L1–L4 default, capability modules | standard |
| L0 meta-architect, L3 escalate, L4 top-2 tie, flagship synthesize, polish audit | flagship |

---

## Research lane (summary)

Eight sequential waves, **38 fields** covering every stage, gate, and major GUI flow. Full catalog + user-flow matrix: [mastering-research-fields.md](./mastering-research-fields.md).

| Wave | Focus |
|------|--------|
| 1 | Source hygiene / ingest / SAP / readiness |
| 2 | Transcript (G0), speakers, topology, volleys, pickup voice, spine |
| 3 | Thesis, value, coherence, coverage, arc candidates, transitions |
| 4 | Segments, brief budgets, episode packs, NLE, ranking, EDL |
| 5 | Gap framing, VO synthesis, framing coverage |
| 6 | Sonic / palettes / soundscape / SDP / MMAudio / mix tiers / profile hints |
| 7 | Journey gates, Conversation Studio, reuse, LLM audit |
| 8 | Lint, EDL QC, completeness, master verify, local runtimes, model tiers |

Rollup: `mastering/research_dossier.json` — **no** final structure yet.

---

## Shape Composition Engine (summary)

Per-podcast custom analysis. Detail: [mastering-shape-engine.md](./mastering-shape-engine.md).

| Level | Job |
|-------|-----|
| L0 Meta-architect | Invent unique `shape/agenda.json` for this source |
| L1 Horizon | Exceptional vs generic risks |
| L2 Candidates | Competitive shape + cold-open hypotheses |
| L3 Deep dive | Strengthen winners; kill weak early |
| L4 Cross-critique | **Excellence filter** — promote best / kill programmatic |
| L5 Convergence | Pre-synthesize brief from survivors only |
| Flagship synthesize | Authoritative `mastering_plan.json` |

**Capability modules** (engine schedules): `cold_open_hook`, `structure_candidates`, `inclusion_exclusion`, `pacing_density`, `vo_sfx_components`.

### Cold open (dynamic)

| `kind` | Meaning |
|--------|---------|
| `none` | Straight into body |
| `segment_hook` | Lift a specific exciting source segment |
| `vo_clone_open` | Pickup-eligible AI clone voice tease |
| `vo_plus_segment` | Clone then segment hook |

SFX is an independent switch on any non-`none` option. Full catalog: [mastering-construction-decisions.md](./mastering-construction-decisions.md).

---

## Realization & Polish

1. Render `cold_open` as leading EDL element(s)
2. Ranking / EDL / transitions / SDP **bound to** `mastering_plan` (including optional `information_packages` and required `episode_close` music — [information-packages.md](./information-packages.md))
3. Before EDL write: rebuild `reorder_bridges` from the air order, **auto-mint pair-specific spoken transitions** for any naked reorder/chapter jump, synthesize audible WAVs, then hard-fail if glue is still missing (NLE soft only)
4. Emit `master/assembly_ledger.json` — air atoms (EDL clips + later mix overlays) labeled by chapter / talking-point spans; seams index must show `naked_seam_count == 0`
5. Preview → optional post-preview pickup when plan requires
6. Mix house chain + mastering mix helpers (evolve `tbiy_mix.py`); refuse selection↔EDL `order_content_hash` drift; always realize gentle `theme_outro` after last native
7. **Junction snip QA + [seam autopsy](./seam-autopsy.md)** — deterministic start/end snip + music-transition repairs on every junction, one feel-audit LLM (`OH-J1`), commitment proof, and at most **two full identify-all → fix-all remediation runs**
8. `master_finalize` → `master/master.wav` (−16 LUFS) → always-on post-master quality + listener scorecard; blocks on naked seams, incomplete `bridge_completeness`, uncommitted repairs, unavailable feel audit, or critical residuals
9. MP3 encoding / podcast package creation requires the same passing post-master quality artifact

Until cutover: if `mastering_plan` is missing, fall back to today’s ranking path (fail-open).

---

## Hard invariants

- Exactly one early synthetic episode orientation (guest, topic, stakes) whenever
  framing is enabled: `native hook → music → orientation → body` for an explicit
  native cold open, otherwise `orientation → music → body`
- The orientation is selection-independent: reordering/exclusion retargets it
  to the final opening instead of dropping it
- Synthetic insertion never removes an approved music asset; a speech-safe,
  sidechain-ducked bed may overlap the orientation when the sonic plan supports it
- Prefer **pickup-eligible** speaker for new VO; **any on-tape speaker** allowed with consent when needed
- Never invent unspoken dialogue / false attributed claims
- Locked **speaker volleys** stay intact through EDL
- **No naked reorder seams:** non-source-contiguous speech adjacencies require pair-specific audible glue (spoken transition or pair-bound gap VO); air-pad silence alone is never enough
- Mechanical loudness QC unchanged (`verify_master`)
- Voice cloning requires consent + approved reference + scope; off-tape cloning is impossible ([mastering-voice-clone-policy.md](./mastering-voice-clone-policy.md))
- No candidate reaches synthesize while infeasible or carrying a critical semantic-integrity finding
- Listen delight is an **authoritative ship gate** (floors in `mastering.listen_delight`); `mode_consistency` alone does not block — delight aggregate does

---

## Artifacts (planned layout)

```
mastering/
  research/routing.json
  research/{field_id}.json
  research_dossier.json
  evidence_packets/{consumer_id}.json
  prompts_minted/...
  shape/agenda.json
  shape/eval_rubric.json
  shape/{module_id}.json
  shape/diversity_report.json
  shape/feasibility.json
  shape/semantic_integrity.json
  shape/cross_critique.json
  shape/pareto.json
  auditions/{candidate_id}/manifest.json
  voice_clone_audit.json
  prompt_edit_log.json
  mastering_plan.json
  polish_audit.json   # heritage; closed-loop polish dropped in v2
```

Also written by delivery realization:

```
master/
  junction_snip_qa.json
  junction_feel_audit.json
```

Schemas: `docs/cross-cutting/json-schemas/artifacts/mastering_*.schema.json`, `junction_snip_qa.schema.json`, `junction_feel_audit.schema.json`  
Prompts: `docs/prompts/mastering/`

---

## Migration

See [mastering-integration-backlog.md](./mastering-integration-backlog.md). Code cutover is staged; this doc is the strategy authority for agents and operators.
