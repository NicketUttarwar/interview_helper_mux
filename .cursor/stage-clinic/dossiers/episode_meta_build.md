# Stage clinic dossier — episode_meta_build

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `episode_meta_build`
- seed_position: 68 (delivery)
- tier (contract claim): llm_full — verified OpenAI
- primary_artifact_path (SSOT claim): publish/episode_meta.json
- immediate upstream producers (from code — L1): soft brief/narrative/selection (`_build_meta_input` fail-soft)
- immediate downstream consumers: cover_prompt, cover_gen, podcast_publish
- gate_adjacency: none (ship walk)
- LLM?: OpenAI publishing/episode-meta.system.txt (flagship)
- thrash_hotspot: no
- test_gravity: thin

## Evidence checklist (§5.1–5.6)

- [x] Complete — OpenAI in clinic

## Links

- Contract: `docs/cross-cutting/stage-contracts/episode_meta_build.yaml`
- Map: `.cursor/stage-clinic/maps/episode_meta_build.possibility.md`
- Target: `.cursor/stage-clinic/targets/episode_meta_build.target.md`
- Notes: `.cursor/stage-clinic/notes/episode_meta_build.decisions.md`
- Module (L1): `stages/podcast_publish.py::run_episode_meta_build`
- Tests (L1): conformance/fixtures (thin)

## Pack completeness

discovery_status: complete
