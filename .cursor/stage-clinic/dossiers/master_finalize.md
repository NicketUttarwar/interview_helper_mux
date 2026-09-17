# Stage clinic dossier — master_finalize

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `master_finalize`
- seed_position: 66 (delivery)
- tier (contract claim): process — authoritative ship gate host
- primary_artifact_path (SSOT claim): master/master.wav (+ post_master_quality.json)
- immediate upstream producers (from code — L1): assembly, edl, junction commitment, render_ledger, seat preflight; soft delight rewritten at ship
- immediate downstream consumers: master_transcript_build, podcast_encode_mp3, podcast_publish
- gate_adjacency: require_g_listen_clear; timeline optimizer; PMQ+authoritative listen_delight; mark_g_publish_pending
- LLM?: indirect via delight/PMQ dimensions — in clinic as ship variance
- thrash_hotspot: medium — optimizer→re-run junction; delight remutate
- test_gravity: solid — test_mastering, listen_delight, post_master_quality, ship

## Evidence checklist (§5.1–5.6)

- [x] Complete; listen_delight ship authority mapped (pre-mix stage skipped as already done)

## Links

- Contract: `docs/cross-cutting/stage-contracts/master_finalize.yaml`
- Map: `.cursor/stage-clinic/maps/master_finalize.possibility.md`
- Target: `.cursor/stage-clinic/targets/master_finalize.target.md`
- Notes: `.cursor/stage-clinic/notes/master_finalize.decisions.md`
- Module (L1): `stages/mastering.py::run_master_finalize` → master_wav + `run_post_master_quality`
- Tests (L1): test_mastering.py, test_listen_delight.py, test_post_master_quality.py

## Pack completeness

discovery_status: complete
