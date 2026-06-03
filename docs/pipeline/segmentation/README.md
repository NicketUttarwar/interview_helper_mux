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

- Prefer splits at pauses ≥ ~700 ms and topic shifts
- Do not split mid-sentence unless STT recovery

## Prompts

- [boundary-detection.system.txt](../../prompts/segmentation/boundary-detection.system.txt)
- [segment-classification.system.txt](../../prompts/segmentation/segment-classification.system.txt)

## Models

| Stage | Tier (default) | Decompose | Validated on-disk path |
|-------|----------------|-----------|------------------------|
| `boundary_detection` | flagship | yes | `segments/boundaries.json` |
| `segment_classification` | flagship | yes | `segments/manifest.json` |

Gap-fill and schema validation: [artifact-generation-and-validation.md](../../cross-cutting/artifact-generation-and-validation.md).

[llm-stage-model-matrix.md](../../cross-cutting/llm-stage-model-matrix.md)

## Module

`src/interview_mux/stages/segmentation.py`

---

## Build-out

BUILD-024 · [README.md](../../build-out/README.md) · [repository-map.md](../../build-out/repository-map.md)
