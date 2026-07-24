# TBIY Flow 1 Production Profile (historical)

> **Superseded as strategy authority by the [Mastering Process](./mastering-process.md).** TBIY was the original Wondery-style inspiration; the product has evolved past enforcing five-act / moat / dual-voice. Retained discipline: pickup-eligible VO only, never invent guest evidence, speech-wins ducking. Migration: [mastering-integration-backlog.md](./mastering-integration-backlog.md).

Wondery-style **compass** (legacy) for Flow 1 full podcast masters — not a rigid template. Prefer Mastering Process Shape Engine for new work.

## Production styles

| Style | Config key | Behavior |
|-------|------------|----------|
| Documentary | `documentary_interview` (default) | Existing sparse SFX; no act/moat QC |
| TBIY narrative | `tbiy_narrative` | Five-act bias, moat, spatial SFX, topology + graduated conformance |

Set via **Profile gate** → `analysis_state.meta.production_style` or `run_meta.production_style`.

Selecting TBIY does **not** flip back to documentary when classic dual-host ingredients are weak. Missing frame pieces become VO bridges; sparse narrative collapses acts; weak moat stays soft — guest evidence is never invented.

## Graduated conformance (`tbiy_conformance`)

Built at `source_topology_build` and refreshed at `delivery_brief_build` (after content brief / gaps).

Artifact field: `understanding/flow_adaptation.json` → `tbiy_conformance` (also mirrored into `delivery_brief`).

| Layer | Behavior |
|-------|----------|
| Element inventory | Detects reactor/frame texture, storyteller dominance, act-bridge need, five-act capacity, moat, era tags, punctuators, pickup voice |
| Per-element action | `apply` · `soft` · `vo_bridge` · `collapse` · `defer` · `operator_only` |
| Modes | `five_act_mode` (`full`/`soft`/`collapsed`), `moat_mode` (`require`/`soft`/`defer`), `vo_bridge_priority` (`high`/`normal`/`low`) |
| Hard lint | Only when mode is `full` / `require` — soft/collapse/defer never force documentary fallback |

Implementation: `src/interview_mux/tbiy_conformance.py`. Thresholds: `production_profiles.tbiy_narrative.conformance.thresholds`. Profile intent flags: `adaptation_defaults.require_moat` / `require_five_act_coverage` (now consumed).

## Hard invariant: pickup voice

**Only the least-spoken speaker** may receive new `vo_pickup/` recordings. Content/guest speakers are trim/reorder only. Enforced in:

- `source_topology_build` → `pickup_eligible_speaker_id`
- `optimal_questions` persist + deterministic lint
- `POST /api/runs/{id}/vo/{line_id}` validation

## Source topology classes

`one_on_one_asymmetric` · `one_on_one_balanced` · `panel_multi_guest` · `co_host_frame` · `multi_idea_sparse_host` · `monologue_heavy`

Artifacts: `understanding/source_topology.json`, `understanding/flow_adaptation.json`

## Operator GUI

- **Story Board** — topology summary (`FlowAdaptationCard`) with conformance score/moves, `production_style`, strategic moat
- **Conversation Studio** — gap-report CRUD (`POST/PATCH/DELETE /api/runs/{id}/gap-report/lines`)
- **G1 VO pickup** — record/trim with boundary suggest; post-preview lines after assembly preview
- **G1.5 gate + panel** — stage `g1_5_preview_pickup` in pipeline; blocks `mmaudio_sfx` until post-preview re-records (`post_preview_recorded_at` in VO metadata). **First-try does not skip** TBIY G1.5 when `post_preview` lines exist (documentary runs typically have none).

## Sign-off checklist

Listen to `master.wav` on ≥3 topology fixtures:

- [ ] Five-act arc perceptible (or intentionally collapsed on monologue)
- [ ] Strategic moat named in act IV region when evidence supports
- [ ] Reactor punctuations or VO bridges on asymmetric/balanced / sparse-frame sources
- [ ] Dialogue intelligible; beds duck under speech
- [ ] Documentary control run unchanged

## Deferred

Flow 2/3 abstraction — see plan **Later** section.
