# Mastering Process (canonical)

> **One interview → one bespoke `master/master.wav`.** Structure emerges from source + assets + operator intent — never from a fixed template.

**TBIY heritage:** [tbiy-production-profile.md](./tbiy-production-profile.md) was the original Wondery-style compass. The Mastering Process **evolves past TBIY**. Five-act / moat / dual-voice are optional tools when evidence supports them — not an enforced compass. Useful TBIY discipline retained: **prefer pickup-eligible (least-spoken) voice for new VO** (any on-tape speaker allowed with consent when needed); never invent unspoken dialogue; speech-wins ducking under speaker volleys.

**Reliability layer:** [mastering-quality-hardening.md](./mastering-quality-hardening.md) — routing, evidence packets, diversity, feasibility, semantic integrity, clone consent, auditions, multi-critic L4, Pareto, closed-loop polish. Gates default to `advisory` and fail open.

**Narrative excellence:** [narrative-mode-and-montage.md](./narrative-mode-and-montage.md) — two-pass Shape (`narrative_mode` + `montage_grammar`), 8-wave research dossier, listen delight always advisory.

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

> Produce the **absolute best** final podcast construction for *this* tape — the most impressive, compelling, information-rich listen — as a **bespoke** combination of components, not a programmatic or repetitive template.

**System-instruction pillars** (every minted/edited shape prompt; L4 especially):

1. Best final outcome for the listener
2. Promote excellence (unequal options)
3. Filter ruthlessly (kill dull / generic / padded)
4. Bespoke, not programmatic
5. Non-repetitive
6. Best *ensemble* (cold open + body + VO/SFX + close)
7. Convey real knowledge (no invented unspoken dialogue)
8. Impressive when earned (restraint otherwise)
9. **Worth finishing / lovable when earned** — finishability and recommendability (always advisory; never hard-block master)

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
2. Ranking / EDL / transitions / SDP **bound to** `mastering_plan`
3. Before EDL write: rebuild `reorder_bridges` from the air order, **auto-mint pair-specific spoken transitions** for any naked reorder/chapter jump, synthesize audible WAVs, then hard-fail if glue is still missing (NLE soft only)
4. Emit `master/assembly_ledger.json` — air atoms (EDL clips + later mix overlays) labeled by chapter / talking-point spans; seams index must show `naked_seam_count == 0`
5. Preview → optional post-preview pickup when plan requires
6. Mix house chain + mastering mix helpers (evolve `tbiy_mix.py`); refuse selection↔EDL `order_content_hash` drift
7. Flagship **audio-grounded** polish audit → bounded remux ([mastering-audition-loop.md](./mastering-audition-loop.md))
8. `master_finalize` → `master/master.wav` (−16 LUFS); blocks on naked seams / incomplete `bridge_completeness`

Until cutover: if `mastering_plan` is missing, fall back to today’s ranking path (fail-open).

---

## Hard invariants

- Prefer **pickup-eligible** speaker for new VO; **any on-tape speaker** allowed with consent when needed
- Never invent unspoken dialogue / false attributed claims
- Locked **speaker volleys** stay intact through EDL
- **No naked reorder seams:** non-source-contiguous speech adjacencies require pair-specific audible glue (spoken transition or pair-bound gap VO); air-pad silence alone is never enough
- Mechanical loudness QC unchanged (`verify_master`)
- Voice cloning requires consent + approved reference + scope; off-tape cloning is impossible ([mastering-voice-clone-policy.md](./mastering-voice-clone-policy.md))
- No candidate reaches synthesize while infeasible or carrying a critical semantic-integrity finding
- Listen delight / mode_consistency never block `master_finalize`

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
  polish_audit.json
```

Schemas: `docs/cross-cutting/json-schemas/artifacts/mastering_*.schema.json`  
Prompts: `docs/prompts/mastering/`

---

## Migration

See [mastering-integration-backlog.md](./mastering-integration-backlog.md). Code cutover is staged; this doc is the strategy authority for agents and operators.
