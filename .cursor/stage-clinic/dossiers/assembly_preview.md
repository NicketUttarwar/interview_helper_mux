# Stage clinic dossier — assembly_preview

brain: 0.2.0 | mode_focus: partially_accelerated | campaign_goal: full_auto_defaults
wave: analysis | L1_map: complete | L2_target: draft | L3_patch: not_started

## §5.0 Evidence index card

- stage_id: `assembly_preview`
- seed_position: 59 (delivery)
- tier (contract claim): process — verified
- primary_artifact_path (SSOT claim): master/assembly_preview.wav
- immediate upstream producers (from code — L1): edl (+ selection soft); ingest normalized soft
- immediate downstream consumers: music deferred pin; mix/junction consumers claim
- gate_adjacency: none; music_deferred may pin this stage
- LLM?: no
- thrash_hotspot: yes — heard_wav refuse → vo_synthesize; EDL heal writeback gate
- test_gravity: solid (`test_assembly_vo_source_heal.py`, HE heard paths)

## Evidence checklist (§5.1–5.6)

- [x] §5.1–5.6 all

## Links

- Contract: `docs/cross-cutting/stage-contracts/assembly_preview.yaml`
- Map: `.cursor/stage-clinic/maps/assembly_preview.possibility.md`
- Target: `.cursor/stage-clinic/targets/assembly_preview.target.md`
- Notes: `.cursor/stage-clinic/notes/assembly_preview.decisions.md`
- Module (L1): `src/interview_mux/stages/assembly.py::run_preview` (pipeline `assembly_preview`)
- Tests (L1): `tests/test_assembly_vo_source_heal.py`

## Pack completeness

discovery_status: complete
