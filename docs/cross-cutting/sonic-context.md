# Sonic context (BUILD-SFX)

`understanding/sonic_context.json` is the compact bridge between interview understanding and sound-design planning.

It gives downstream sound stages one shared source of:

- scenario posture (`atlas_bucket`, `sound_posture`)
- provenance-grounded thematic tags (`tag_registry`)
- cue opportunities (`cue_opportunities`)
- mix constraints (`mix_policy`)
- hard bans and risk flags (`avoid_hard`, `segment_flags`)

## Producer and consumers

- **Producer stage:** `sonic_context_build`
- **Primary consumers:** `sound_design_palettes`, `sound_design_plan`, `REMOVED_sdp_flow2`, `sfx_prompt_craft`, `sfx_prompt_refine`, mix/post-QA guidance
- **GUI surface:** `SonicContextPanel` in stage detail context panels

## Contract

- **Schema:** `docs/cross-cutting/json-schemas/sonic_context.schema.json`
- **Run artifact path:** `understanding/sonic_context.json`
- `version` is currently fixed at `1`

## Authoring rules

- Every `tag_registry` row must include `provenance` and should map to concrete upstream evidence (brief/topic/tags/segments).
- Scenario posture is authoritative for density/cadence defaults; downstream prompts should not override it without explicit operator rationale.
- `cue_opportunities` should point to real segment/clip anchors only (no fabricated timeline references).

## Relation to sound design plan

`understanding/sound_design_plan.json` may carry `sonic_context_hash` so planning/craft artifacts can be invalidated or reused when context changes.
