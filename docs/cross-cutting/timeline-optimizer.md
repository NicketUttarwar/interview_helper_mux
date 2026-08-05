# Timeline optimizer (endless mid-mix search)

Per-run **mode C** daemon: after the first shippable `mix`, keep permuting the timeline to hunt a more finishable, beautiful podcast. Operator can **Take best**, **Stop**, or let it run while shipping.

## Defaults (full-auto)

| Key | Default | Meaning |
|-----|---------|---------|
| `mastering.timeline_optimizer.enabled` | `true` | Master switch |
| `mode` | `endless_daemon` | Continues after plateau (soft promote, then keep searching) |
| `mutation_surface` | `maximum` | Structure + glue VO/transitions + SDP cues + LLM proposals |
| `auto_start_after_mix` | `true` | Starts when mix completes |
| `use_llm_proposer` | `true` | Every N gens, flagship proposes mutations |
| `block_finalize_until_take_or_skip` | `true` | Finalize waits for optimizer authority | `false` permits finalize before take/skip |

## Mutation surface (maximum)

- **Structure:** hook early, topo repair, swap, rotate, exclude, drop redundant split siblings, Shape/chapter `set_order`
- **Glue:** mint/rewrite bridges, gap line hints (Chatterbox on remaster)
- **Sound:** remap cold-open theme, hinge punctuators
- **LLM:** `docs/prompts/mastering/timeline-optimizer-propose.system.txt`

## Artifacts

- `master/optimizer/state.json` — daemon status
- `master/optimizer/archive.json` — Pareto-ish candidates
- `master/optimizer/best_candidate.json` — current champion

## API

- `GET /api/runs/{id}/timeline-optimizer`
- `POST …/start` · `…/stop` · `…/take-best` · `…/skip`

## Relation to prior story-placement plan

Stage ranking / bridges / story_health remain the **seed**. This daemon is the **open-ended search** layered on top for each tape.
