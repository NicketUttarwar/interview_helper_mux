# TBIY Flow 1 Production Profile

Wondery-style **compass** for Flow 1 full podcast masters — not a rigid template.

## Production styles

| Style | Config key | Behavior |
|-------|------------|----------|
| Documentary | `documentary_interview` (default) | Existing sparse SFX; no act/moat QC |
| TBIY narrative | `tbiy_narrative` | Five-act bias, moat, spatial SFX, topology adaptation |

Set via **Profile gate** → `analysis_state.meta.production_style` or `run_meta.production_style`.

## Hard invariant: pickup voice

**Only the least-spoken speaker** may receive new `vo_pickup/` recordings. Content/guest speakers are trim/reorder only. Enforced in:

- `source_topology_build` → `pickup_eligible_speaker_id`
- `optimal_questions` persist + deterministic lint
- `POST /api/runs/{id}/vo/{line_id}` validation

## Source topology classes

`one_on_one_asymmetric` · `one_on_one_balanced` · `panel_multi_guest` · `co_host_frame` · `multi_idea_sparse_host` · `monologue_heavy`

Artifacts: `understanding/source_topology.json`, `understanding/flow_adaptation.json`

## Operator GUI

- **Story Board** — topology summary (`FlowAdaptationCard`), `production_style`, strategic moat
- **Conversation Studio** — gap-report CRUD (`POST/PATCH/DELETE /api/runs/{id}/gap-report/lines`)
- **G1 VO pickup** — record/trim with boundary suggest; post-preview lines after assembly preview
- **G1.5 gate + panel** — stage `g1_5_preview_pickup` in pipeline; blocks `mmaudio_sfx_flow1` until post-preview re-records (`post_preview_recorded_at` in VO metadata)

## Sign-off checklist

Listen to `master.wav` on ≥3 topology fixtures:

- [ ] Five-act arc perceptible
- [ ] Strategic moat named in act IV region
- [ ] Reactor punctuations on asymmetric/balanced sources
- [ ] Dialogue intelligible; beds duck under speech
- [ ] Documentary control run unchanged

## Deferred

Flow 2/3 abstraction — see plan **Later** section.
