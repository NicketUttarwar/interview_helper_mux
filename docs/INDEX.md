# Documentation index

Flat hub for **interview_helper_mux**.

## Roadmap — future-proofing

- [roadmap/future-proofing.md](./roadmap/future-proofing.md) — **guardrails** + compact idea directions for future analysis/features (audio-only)
- [roadmap/README.md](./roadmap/README.md) — pointer to the above
- [pipeline/value-analysis/README.md](./pipeline/value-analysis/README.md) — optional: spike rubrics, moonshots (read [future-proofing](./roadmap/future-proofing.md) first)

## Core specs

- [README.md](./README.md) — doc overview
- [pipeline.md](./pipeline.md) — three output flows, operator gates
- [logic-tree.md](./logic-tree.md) — gap detection and decisions
- [prompts/README.md](./prompts/README.md) — LLM prompt tree
- [prompts/sound_design/README.md](./prompts/sound_design/README.md) — sound-design LLM stages + ElevenLabs craft
- [prompts/sound_design/guardrails-and-edge-cases.md](./prompts/sound_design/guardrails-and-edge-cases.md) — SDP/mix guardrails (Wave 5)
- [prompts/_shared/examples/sound-design.examples.md](./prompts/_shared/examples/sound-design.examples.md) — rich ElevenLabs prompt examples

## Cross-cutting

- [cross-cutting/anchored-toolchain.md](./cross-cutting/anchored-toolchain.md) — **pinned** Python, system binaries, API surfaces, lock + CVE gate + Context7
- [cross-cutting/anchored-requirements.lock](./cross-cutting/anchored-requirements.lock) — doc snapshot of lock pins (install from repo-root `requirements.lock`)
- [cross-cutting/elevenlabs-integration-guide.md](./cross-cutting/elevenlabs-integration-guide.md) — **canonical** ElevenLabs REST SFX + isolation, GUI journey, post-analysis
- [cross-cutting/elevenlabs-prompt-influence-tuning.md](./cross-cutting/elevenlabs-prompt-influence-tuning.md) — `prompt_influence` symptom table
- [prompts/_shared/examples/elevenlabs-prompt-regression.md](./prompts/_shared/examples/elevenlabs-prompt-regression.md) — golden prompts + must-not-hear QA
- [cross-cutting/podcast-quality-roadmap.md](./cross-cutting/podcast-quality-roadmap.md) — v1 vs target master, priority waves, quality offers
- [cross-cutting/analysis-memory.md](./cross-cutting/analysis-memory.md) — per-interview profile, operator edits
- [cross-cutting/context-padding.md](./cross-cutting/context-padding.md) — what each LLM call receives
- [cross-cutting/segment-schema.md](./cross-cutting/segment-schema.md)
- [cross-cutting/artifact-layout.md](./cross-cutting/artifact-layout.md)
- [cross-cutting/json-schema-coverage.md](./cross-cutting/json-schema-coverage.md) — schema gaps, fixes, guards
- [cross-cutting/json-schemas/README.md](./cross-cutting/json-schemas/README.md) — schema index + conventions
- [cross-cutting/model-routing.md](./cross-cutting/model-routing.md) — tier registry (API IDs in one place)
- [cross-cutting/llm-orchestration.md](./cross-cutting/llm-orchestration.md) — arbiter, shard/collate, task_kind (**spec**)
- [cross-cutting/llm-stage-model-matrix.md](./cross-cutting/llm-stage-model-matrix.md) — per-stage tier and severity
- [cross-cutting/llm-orchestration-implementation-handoff.md](./cross-cutting/llm-orchestration-implementation-handoff.md) — future code mapping
- [prompts/_shared/llm-arbiter-contract.md](./prompts/_shared/llm-arbiter-contract.md) — arbiter JSON contract
- [cross-cutting/sound-design.md](./cross-cutting/sound-design.md) — coherent reusable SFX (planned, BUILD-060+)
- [cross-cutting/source-derived-sonic-mix-profile.md](./cross-cutting/source-derived-sonic-mix-profile.md) — per-interview acoustic/pacing profile from source audio (planned)
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
- [pipeline/value-analysis/README.md](./pipeline/value-analysis/README.md) — value-forward analysis research (moonshots, Phase 3 spikes; audio-only)
- [pipeline/understanding/README.md](./pipeline/understanding/README.md)
- [pipeline/segmentation/README.md](./pipeline/segmentation/README.md)
- [pipeline/interviewer-gap/README.md](./pipeline/interviewer-gap/README.md)
- [pipeline/scoring_and_selection/README.md](./pipeline/scoring_and_selection/README.md)
- [pipeline/audio_editing/README.md](./pipeline/audio_editing/README.md)
- [pipeline/assembly_and_mux/README.md](./pipeline/assembly_and_mux/README.md)
- [pipeline/mastering_and_export/README.md](./pipeline/mastering_and_export/README.md)
- [pipeline/publishing/README.md](./pipeline/publishing/README.md) — Flow 3 show description (text)

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

- [build-out/implementation-guide.md](./build-out/implementation-guide.md) — **master plan**: all phases, waves, definition of done
- [build-out/full-application-flow.md](./build-out/full-application-flow.md) — end-to-end operator + system journey
- [build-out/stage-registry.md](./build-out/stage-registry.md) — every stage id, module, artifact, status
- [build-out/ticket-specs.md](./build-out/ticket-specs.md) — acceptance criteria per BUILD ticket
- [build-out/README.md](./build-out/README.md) — numbered tickets (Waves 0–7)
- [build-out/steps-forward.md](./build-out/steps-forward.md) — prioritized backlog
- [build-out/repository-map.md](./build-out/repository-map.md) — repo layout ↔ modules ↔ docs
- [build-out/testing-and-verification.md](./build-out/testing-and-verification.md) — verify each wave
- [build-out/doc-maintenance.md](./build-out/doc-maintenance.md) — docs to update per PR
