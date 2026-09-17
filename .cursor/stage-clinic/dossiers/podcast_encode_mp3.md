# Stage clinic dossier — podcast_encode_mp3

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `podcast_encode_mp3`
- seed_position: 70 (delivery)
- tier (contract claim): process — ffmpeg host
- primary_artifact_path (SSOT claim): publish/audio.mp3 (+ publish/master.wav copy)
- immediate upstream producers (from code — L1): master/master.wav; require_publishable
- immediate downstream consumers: podcast_publish
- gate_adjacency: none
- LLM?: no
- thrash_hotspot: no
- test_gravity: thin (HPUB-1)

## Evidence checklist (§5.1–5.6)

- [x] Complete

## Links

- Contract: `docs/cross-cutting/stage-contracts/podcast_encode_mp3.yaml`
- Map: `.cursor/stage-clinic/maps/podcast_encode_mp3.possibility.md`
- Target: `.cursor/stage-clinic/targets/podcast_encode_mp3.target.md`
- Notes: `.cursor/stage-clinic/notes/podcast_encode_mp3.decisions.md`
- Module (L1): `podcast_publish.run_podcast_encode_mp3`
- Tests (L1): HPUB-1 filters

## Pack completeness

discovery_status: complete
