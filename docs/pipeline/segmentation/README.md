# Segmentation

Boundary detection and segment classification.

## Tickets

BUILD-024, BUILD-025

## Tools

**OpenAI** Chat Completions — [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md) · [model-routing.md](../../cross-cutting/model-routing.md)

## Inputs

| Path | Description |
|------|-------------|
| `transcript/full.json` | Word-level text |
| `understanding/speakers.json` | Roles |
| `understanding/content_brief.json` | Topics |

## Outputs

| Path | Description |
|------|-------------|
| `segments/boundaries.json` | Proposed splits |
| `segments/manifest.json` | Classified segments |

## Rules

- **Fine granularity (default):** maximize edit-ready segments for reordering, gap VO, and SFX anchors
- Split long same-speaker spans at **topic/idea** boundaries using `content_brief.topics[]`, not pauses alone
- Split interviewer **backchannels** into standalone segments when diarization shows a brief host turn
- Prefer splits at pauses ≥ ~400 ms (configurable via `pause_split_ms`); enforce `max_segment_duration_ms` when set
- Do not split mid-sentence unless STT recovery
- **Timeline authority:** `segments/boundaries.json` + `_meta.segment_contract` owns IDs and times; manifest is semantic overlay ([segment-schema.md](../../cross-cutting/segment-schema.md))
- **Unified review** (`journey_ui.segmentation_unified_review`): boundary stages without Save pause; paired review/save at `segment_classification` ([gui-surface-map.md](../../workflows/gui-surface-map.md))
- **Post-reanchor:** `boundary_topic_resplit` splits overloaded segments using reanchored topic ↔ segment mapping

## Hardening (shipped)

- Per-shard boundary normalize + reject (`segment_timeline_standard.py`)
- Deterministic enrich: backchannel split + max-duration force split (`boundary_enrich.py`)
- Deterministic collate authority for boundaries and classification
- Field parity + reference closure via `segmentation_input_resolver.py`
- Config: `analysis.segmentation.*` — see [config-keys.md](../../cross-cutting/config-keys.md)

## Prompts

- [boundary-detection.system.txt](../../prompts/segmentation/boundary-detection.system.txt)
- [boundary-detection-refine.system.txt](../../prompts/segmentation/boundary-detection-refine.system.txt)
- [segment-classification.system.txt](../../prompts/segmentation/segment-classification.system.txt)

## Models

| Stage | Tier (default) | Decompose | Validated on-disk path |
|-------|----------------|-----------|------------------------|
| `boundary_detection` | flagship | yes | `segments/boundaries.json` |
| `boundary_topic_resplit` | flagship | yes | `segments/boundaries.json` |
| `segment_classification` | flagship | yes | `segments/manifest.json` |

Gap-fill and schema validation: [artifact-generation-and-validation.md](../../cross-cutting/artifact-generation-and-validation.md).

[llm-stage-model-matrix.md](../../cross-cutting/llm-stage-model-matrix.md)

## Module

`src/interview_mux/stages/segmentation.py` · `src/interview_mux/boundary_enrich.py`

---

## Build-out

BUILD-024 · [README.md](../../build-out/README.md) · [repository-map.md](../../build-out/repository-map.md)
