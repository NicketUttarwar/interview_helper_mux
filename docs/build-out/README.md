# Build-out index

Numbered tickets for agent implementation. Status: **implemented** in greenfield v1 unless noted.

## Legend

| Status | Meaning |
|--------|---------|
| done | Shipped in repo |
| planned | Spec in docs; not in code |
| gate | Operator checkpoint |

## Wave 0 — Docs

| Ticket | Title | Deliverable |
|--------|-------|-------------|
| BUILD-000 | Doc index + AGENTS | `docs/INDEX.md`, `AGENTS.md`, `README.md`, `SETUP.md` |
| BUILD-001 | Artifact layout + schemas | `docs/cross-cutting/*` |
| BUILD-002 | Operator gates | `docs/workflows/operator-gates.md` |
| BUILD-003 | Stage READMEs | `docs/pipeline/*/README.md` |
| BUILD-004 | Build-out index | this file |

## Wave 1 — Shell

| Ticket | Title | Module |
|--------|-------|--------|
| BUILD-010 | pyproject + venv | `pyproject.toml`, `scripts/bootstrap_venv.sh` |
| BUILD-011 | Config loader | `src/interview_mux/config.py` |
| BUILD-012 | Run workspace | `src/interview_mux/run_context.py` |
| BUILD-013 | OpenAI runner | `src/interview_mux/stages/llm_runner.py` |

## Wave 2 — Analysis

| Ticket | Title | Module |
|--------|-------|--------|
| BUILD-019 | Audio pre-clean (optional) | `stages/audio_preclean.py` (planned) |
| BUILD-020 | Ingest | `stages/ingest.py` |
| BUILD-021 | AWS Transcribe | `stages/transcribe_aws.py` |
| BUILD-022–027 | LLM analysis | `understanding.py`, `segmentation.py`, `gaps.py` |
| BUILD-028 | Analysis CLI | `tools/run_analysis.py` |

**Gate G1** after BUILD-028 — see [operator-gates.md](../workflows/operator-gates.md)

## Wave 3a — Flow 1

| Ticket | Title | Module | Status |
|--------|-------|--------|--------|
| BUILD-029 | Topic coverage | `analysis_flow1_extended.py` | done |
| BUILD-030 | Narrative arc | `analysis_flow1_extended.py` | done |
| BUILD-031 | Full master ranking | `selection_flow1.py` | done |
| BUILD-032 | Transitions | `selection_flow1.py` | done |
| BUILD-033 | Podcast SFX brief | `selection_flow1.py` | done (v1 brief only) |
| BUILD-034 | ElevenLabs SFX | `sfx_elevenlabs.py` | done (v1 per-cue, no reuse) |
| BUILD-035 | Mux assembly | `assembly_flow1.py` | done (v1 speech-only) |
| BUILD-036 | Master export | `mastering.py` | done |

## Wave 3b — Flow 2

| Ticket | Title | Module | Status |
|--------|-------|--------|--------|
| BUILD-040 | Highlight selection | `selection_flow2.py` | done |
| BUILD-041 | SFX brief | `selection_flow2.py` | done (v1 brief only) |
| BUILD-042 | ElevenLabs SFX | `sfx_elevenlabs.py` | done (v1 index concat) |
| BUILD-043 | Micro-assembly | `assembly_flow2.py` | done |
| BUILD-044 | Master export | `mastering.py` | done |

**Gate G2** before Wave 3 — flow selection in `run_meta.json`

## Wave 4 — QA

| Ticket | Title | Module |
|--------|-------|--------|
| BUILD-050 | Mastering module | `mastering.py` |
| BUILD-051 | Flow CLI | `tools/run_flow.py` |
| BUILD-052 | verify_master | `tools/verify_master.py` |
| BUILD-053 | Smoke test doc | `docs/workflows/smoke-test.md` |

## Wave 5 — Coherent sound design (planned)

**Spec:** [sound-design.md](../cross-cutting/sound-design.md) · **Prompt specs:** [prompts/sound_design/README.md](../prompts/sound_design/README.md)

Replaces v1 BUILD-033/034/041/042/035/043 behavior with analysis-informed, reusable assets and real mux. Implement in order.

| Ticket | Title | Deliverable |
|--------|-------|-------------|
| BUILD-060 | SDP schema + empty plan init | `sound_design_plan.schema.json`, template in run workspace |
| BUILD-061 | Theme palettes stage | `sound_design_palettes` after `segment_classification`; `stages/sound_design_stages.py` |
| BUILD-062 | Flow 1 plan stage | `sound_design_plan_flow1`; prompts; merge into SDP |
| BUILD-063 | Flow 2 plan stage | `sound_design_plan_flow2`; shared transition asset rules |
| BUILD-064 | ElevenLabs prompt craft + generate | `sound_design.py` generate; one WAV per `asset_id` |
| BUILD-065 | Mix engine | `mix_flow1` / `mix_flow2` (pydub); VO + beds + stingers; semantic placement |
| BUILD-066 | Pipeline + GUI wire-up | Replace/alias v1 stages; artifact-layout; optional G1.5 gate doc |

### BUILD-060 acceptance

- JSON Schema validates `understanding/sound_design_plan.json`
- `merge_plan_patch` preserves palettes when flow plan updates

### BUILD-061 acceptance

- Palettes reference real `segment_ids` from manifest
- `coherence.sonic_identity` set from content brief + style

### BUILD-062–063 acceptance

- Every chapter boundary reuses same `asset_id` (Flow 1)
- Every clip transition reuses same `asset_id` (Flow 2)
- Farm (or dominant theme) palette drives `under_segment` beds only on tagged segments

### BUILD-064 acceptance

- `duration_seconds` from craft pass used in ElevenLabs call
- Regenerating run skips existing `generated` assets unless plan hash changes

### BUILD-065 acceptance

- Flow 1 `assembly.wav` includes VO pickup + ducked beds + chapter stingers
- Flow 2 cold open plays before clip 1; transition between ranks 1→2, 2→3, etc.

### BUILD-066 acceptance

- `pipeline.py` ANALYSIS_ORDER includes `sound_design_palettes`
- FLOW orders use `sound_design_plan_flow*` + `sound_design_generate_flow*`
- Backward compat: legacy `podcast_sfx_brief.json` export optional

## Dependency order

```
000 → 001 → 002 → 003 → 004
010 → 011 → 012 → 013
019 (optional) → 020 → 021 → 022…027 → 028 → [G1] → [G2]
029…036 (flow1) OR 040…044 (flow2)
050 → 051 → 052 → 053
060 → 061 → 062 & 063 → 064 → 065 → 066
```

Wave 5 can start after BUILD-013 (LLM runner) and BUILD-028 (analysis CLI); flow tickets 062–063 require G2 flow selection artifacts.

## Wave 6 — Podcast quality wiring (planned)

**Spec:** [podcast-quality-roadmap.md](../cross-cutting/podcast-quality-roadmap.md)

Closes the gap between rich analysis artifacts and a polished `master.wav`.

| Ticket | Title | Deliverable |
|--------|-------|-------------|
| BUILD-067 | Gap report → EDL | `edl_flow1` includes `vo_pickup` + gap placements |
| BUILD-068 | NLE → selection/EDL | `nle_edits.json` applied before ranking or mux |
| BUILD-069 | Assembly preview | `flow_1_master/assembly_preview.wav` (speech + VO, no SFX) |
| BUILD-070 | verify_master LUFS/peak | `tools/verify_master.py` per evaluation-metrics |
| BUILD-071 | Mastering measurement | Two-pass or pyloudnorm on assembly bus |
| BUILD-072 | Pre-clean quality offers | GUI prompts at checkpoints; G1 pickup clean; `scope` in `run_meta.json` |

### BUILD-067 acceptance

- Every `delivery: record` line in EDL with timeline offset
- `transitions.json` consumed or mapped to VO/speech ordering

### BUILD-068 acceptance

- Excluded NLE segments absent from `ordered_segment_ids`
- `sequence_order` overrides LLM order when non-empty

### BUILD-072 acceptance

- Offers at: before ingest, after G0, after G1 pickup save, before mux (documented in operator-gates)
- Pickup-only clean does not invalidate transcript markers

## Dependency order (extended)

```
…
060 → 061 → 062 & 063 → 064 → 065 → 066
067 → 068 → 069 (parallel with 065 where possible)
070 → 071
019 + 072 (pre-clean + offers; 072 can ship after 019)
```
