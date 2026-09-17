# Stage clinic dossier — podcast_publish

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `podcast_publish`
- seed_position: 72 (delivery)
- tier (contract claim): process — local package; S3 sync separate
- primary_artifact_path (SSOT claim): publish/package_ready.json (ready:true)
- immediate upstream producers (from code — L1): master.wav hard claim; body also mp3/cover/VTT/chapters/meta effectively hard
- immediate downstream consumers: none in seed (S3 sync outside stage via sync_assets)
- gate_adjacency: G-Publish (PARTIAL_MUST_ACT); Prepare/Skip GUI; `require_g_publish_clear` **dead (never called)**
- LLM?: no
- thrash_hotspot: no
- test_gravity: solid honesty HPUB-2/3; skip-vs-ready thin; sync advisory thin

## Evidence checklist (§5.1–5.6)

- [x] Complete — thorough G-Publish / Full-auto S3

## Links

- Contract: `docs/cross-cutting/stage-contracts/podcast_publish.yaml`
- Map: `.cursor/stage-clinic/maps/podcast_publish.possibility.md`
- Target: `.cursor/stage-clinic/targets/podcast_publish.target.md`
- Notes: `.cursor/stage-clinic/notes/podcast_publish.decisions.md`
- Module (L1): `podcast_publish.run_podcast_publish` / `run_podcast_publish_skip`
- Tests (L1): HPUB-2/3; sync advisory tests thin

## Pack completeness

discovery_status: complete
