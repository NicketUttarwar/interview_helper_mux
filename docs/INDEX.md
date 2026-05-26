# Documentation index

Flat hub for **interview_helper_mux**.

## Core specs

- [README.md](./README.md) — doc overview
- [pipeline.md](./pipeline.md) — two output flows, operator gates
- [logic-tree.md](./logic-tree.md) — gap detection and decisions
- [prompts/README.md](./prompts/README.md) — LLM prompt tree
- [prompts/sound_design/README.md](./prompts/sound_design/README.md) — planned SFX prompts (BUILD-061–064)
- [prompts/sound_design/guardrails-and-edge-cases.md](./prompts/sound_design/guardrails-and-edge-cases.md) — SDP/mix guardrails (Wave 5)

## Cross-cutting

- [cross-cutting/podcast-quality-roadmap.md](./cross-cutting/podcast-quality-roadmap.md) — v1 vs target master, priority waves, quality offers
- [cross-cutting/analysis-memory.md](./cross-cutting/analysis-memory.md) — per-interview profile, operator edits
- [cross-cutting/context-padding.md](./cross-cutting/context-padding.md) — what each LLM call receives
- [cross-cutting/segment-schema.md](./cross-cutting/segment-schema.md)
- [cross-cutting/artifact-layout.md](./cross-cutting/artifact-layout.md)
- [cross-cutting/json-schema-coverage.md](./cross-cutting/json-schema-coverage.md) — schema gaps, fixes, guards
- [cross-cutting/json-schemas/README.md](./cross-cutting/json-schemas/README.md) — schema index + conventions
- [cross-cutting/model-routing.md](./cross-cutting/model-routing.md)
- [cross-cutting/sound-design.md](./cross-cutting/sound-design.md) — coherent reusable SFX (planned, BUILD-060+)
- [cross-cutting/evaluation-metrics.md](./cross-cutting/evaluation-metrics.md)
- [cross-cutting/config-keys.md](./cross-cutting/config-keys.md) — `app.defaults.json` + secrets merge
- [cross-cutting/json-schemas/](./cross-cutting/json-schemas/)

## Pipeline stages

- [pipeline/capture/README.md](./pipeline/capture/README.md)
- [pipeline/audio_preclean/README.md](./pipeline/audio_preclean/README.md) — optional background-noise removal (ElevenLabs)
- [pipeline/ingest/README.md](./pipeline/ingest/README.md)
- [pipeline/transcription/README.md](./pipeline/transcription/README.md)
- [pipeline/transcription/stt-and-diarization.md](./pipeline/transcription/stt-and-diarization.md)
- [pipeline/transcription/source-separation-and-enhancement.md](./pipeline/transcription/source-separation-and-enhancement.md)
- [pipeline/transcription/transcript-review.md](./pipeline/transcription/transcript-review.md)
- [pipeline/understanding/README.md](./pipeline/understanding/README.md)
- [pipeline/segmentation/README.md](./pipeline/segmentation/README.md)
- [pipeline/interviewer-gap/README.md](./pipeline/interviewer-gap/README.md)
- [pipeline/scoring_and_selection/README.md](./pipeline/scoring_and_selection/README.md)
- [pipeline/audio_editing/README.md](./pipeline/audio_editing/README.md)
- [pipeline/assembly_and_mux/README.md](./pipeline/assembly_and_mux/README.md)
- [pipeline/mastering_and_export/README.md](./pipeline/mastering_and_export/README.md)

## Workflows

- [workflows/analysis-orchestration-loop.md](./workflows/analysis-orchestration-loop.md)
- [workflows/operator-gates.md](./workflows/operator-gates.md)
- [workflows/idempotent-runs.md](./workflows/idempotent-runs.md)
- [workflows/feedback-loops-and-reruns.md](./workflows/feedback-loops-and-reruns.md)
- [workflows/operator-stage-checklists.md](./workflows/operator-stage-checklists.md)
- [workflows/gui-surface-map.md](./workflows/gui-surface-map.md) — panels ↔ API ↔ logs ↔ artifacts
- [workflows/api-reference.md](./workflows/api-reference.md) — FastAPI `/api/*` routes, bodies, errors
- [workflows/long-interview-chunking.md](./workflows/long-interview-chunking.md) — context caps policy
- [workflows/troubleshooting.md](./workflows/troubleshooting.md)
- [workflows/smoke-test.md](./workflows/smoke-test.md)

## Agent build-out

- [build-out/README.md](./build-out/README.md)
