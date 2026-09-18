# Stage clinic dossier — episode_cover_generate

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: remediation | L1_map: complete | L2_target: draft | L3_patch: done

## §5.0 Evidence index card

- stage_id: `episode_cover_generate`
- seed_position: 71 (delivery)
- tier (contract claim): llm_full — OpenAI Images+Vision (ECG-B2)
- primary_artifact_path (SSOT claim): publish/cover.jpg (+ pick/meta/candidates)
- immediate upstream producers (from code — L1): cover_prompt soft-harvest; meta/brief soft
- immediate downstream consumers: podcast_publish
- gate_adjacency: none
- LLM?: OpenAI image gen (×3) + vision pick (`pick_cover_winner`); cascade matches podcast-cover-theme claim
- thrash_hotspot: max_rebatch=1 only
- test_gravity: solid — HPUB-2, F7, ECG-B1/B2/B3 pins

## Evidence checklist (§5.1–5.6)

- [x] Complete — OpenAI cover cascade in clinic

## Links

- Contract: `docs/cross-cutting/stage-contracts/episode_cover_generate.yaml`
- Map: `.cursor/stage-clinic/maps/episode_cover_generate.possibility.md`
- Target: `.cursor/stage-clinic/targets/episode_cover_generate.target.md`
- Notes: `.cursor/stage-clinic/notes/episode_cover_generate.decisions.md`
- Module (L1): `podcast_publish.run_episode_cover_generate` + `cover_vision.pick_cover_winner`
- Tests (L1): HPUB-2, F7 generate retry; ECG ownership + tier pins

## Pack completeness

discovery_status: complete
