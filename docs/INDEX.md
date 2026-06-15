# Documentation index

Flat hub for **interview_helper_mux**.

## Operator (start here)

- [workflows/operator-journey.md](./workflows/operator-journey.md) — **primary** happy path (Prepare → Ship)
- [workflows/operator-flow-audit.md](./workflows/operator-flow-audit.md) — full GUI flows, modals, resolved UX audit
- [workflows/operator-gates.md](./workflows/operator-gates.md) — G0, G1, G2, quality offers
- [workflows/operator-sound-and-mix.md](./workflows/operator-sound-and-mix.md) — SAP → SDP → preview → mix
- [workflows/troubleshooting.md](./workflows/troubleshooting.md)
- [workflows/legacy-and-compat.md](./workflows/legacy-and-compat.md) — CLI, legacy stages, `data/run_*`
- [cross-cutting/assets-and-executions.md](./cross-cutting/assets-and-executions.md)

## Roadmap — future-proofing

- [roadmap/future-proofing.md](./roadmap/future-proofing.md) — **guardrails** + compact idea directions for future analysis/features (audio-only)
- [roadmap/README.md](./roadmap/README.md) — pointer to the above
- [pipeline/value-analysis/README.md](./pipeline/value-analysis/README.md) — optional: spike rubrics, moonshots (read [future-proofing](./roadmap/future-proofing.md) first)

## Core specs

- [README.md](./README.md) — doc overview
- [pipeline.md](./pipeline.md) — three output flows, operator gates
- [logic-tree.md](./logic-tree.md) — gap detection and decisions
- [prompts/README.md](./prompts/README.md) — LLM prompt tree
- [prompts/sound_design/README.md](./prompts/sound_design/README.md) — sound-design LLM stages + MMAudio prompt craft
- [prompts/sound_design/guardrails-and-edge-cases.md](./prompts/sound_design/guardrails-and-edge-cases.md) — SDP/mix guardrails (Wave 5)
- [prompts/_shared/examples/sound-design.examples.md](./prompts/_shared/examples/sound-design.examples.md) — rich MMAudio prompt examples

## Cross-cutting

- [cross-cutting/anchored-toolchain.md](./cross-cutting/anchored-toolchain.md) — **pinned** Python, system binaries, API surfaces, lock + CVE gate + Context7
- [cross-cutting/anchored-requirements.lock](./cross-cutting/anchored-requirements.lock) — doc snapshot of lock pins (install from repo-root `requirements.lock`)
- [cross-cutting/local-audio-stack.md](./cross-cutting/local-audio-stack.md) — **canonical** local MMAudio SFX + DeepFilterNet preclean, GUI journey, post-analysis
- [cross-cutting/mmaudio-prompt-tuning.md](./cross-cutting/mmaudio-prompt-tuning.md) — CFG, negative prompts, refine/regen operator loop
- [prompts/_shared/examples/sfx-prompt-regression.md](./prompts/_shared/examples/sfx-prompt-regression.md) — golden prompts + must-not-hear QA
- [cross-cutting/podcast-quality-roadmap.md](./cross-cutting/podcast-quality-roadmap.md) — v1 vs target master, priority waves, quality offers
- [cross-cutting/analysis-memory.md](./cross-cutting/analysis-memory.md) — per-interview profile, operator edits
- [cross-cutting/artifact-generation-and-validation.md](./cross-cutting/artifact-generation-and-validation.md) — flagship LLM artifacts, gap-fill, JSON Schema + Zod validation
- [cross-cutting/context-padding.md](./cross-cutting/context-padding.md) — what each LLM call receives
- [cross-cutting/segment-schema.md](./cross-cutting/segment-schema.md)
- [cross-cutting/assets-and-executions.md](./cross-cutting/assets-and-executions.md) — **ASSETS/** source picker, executions, resume
- [cross-cutting/artifact-layout.md](./cross-cutting/artifact-layout.md)
- [cross-cutting/json-schema-coverage.md](./cross-cutting/json-schema-coverage.md) — schema gaps, fixes, guards
- [cross-cutting/json-schemas/README.md](./cross-cutting/json-schemas/README.md) — schema index + conventions
- [cross-cutting/model-routing.md](./cross-cutting/model-routing.md) — tier registry (API IDs in one place)
- [cross-cutting/llm-orchestration.md](./cross-cutting/llm-orchestration.md) — smart LLM routing: arbiter, tiers, shard/collate (BUILD-073)
- [cross-cutting/llm-stage-model-matrix.md](./cross-cutting/llm-stage-model-matrix.md) — per-stage tier and severity
- [cross-cutting/llm-orchestration-implementation-handoff.md](./cross-cutting/llm-orchestration-implementation-handoff.md) — future code mapping
- [cross-cutting/llm-call-record-framework.md](./cross-cutting/llm-call-record-framework.md) — labeled storage for every OpenAI call + volley reconstruction
- [cross-cutting/local-llm-tier.md](./cross-cutting/local-llm-tier.md) — on-device MLX volley framing (structured artifacts still use OpenAI flagship)
- [cross-cutting/local-llm-implementation-handoff.md](./cross-cutting/local-llm-implementation-handoff.md) — local LLM wiring checklist
- [prompts/_shared/llm-arbiter-contract.md](./prompts/_shared/llm-arbiter-contract.md) — arbiter JSON contract
- [cross-cutting/sound-design.md](./cross-cutting/sound-design.md) — coherent reusable SFX (shipped; [Wave 5 done](./build-out/README.md#wave-5--coherent-sound-design-done))
- [cross-cutting/source-derived-sonic-mix-profile.md](./cross-cutting/source-derived-sonic-mix-profile.md) — per-interview acoustic/pacing profile from source audio (shipped, BUILD-082)
- [cross-cutting/evaluation-metrics.md](./cross-cutting/evaluation-metrics.md)
- [cross-cutting/config-keys.md](./cross-cutting/config-keys.md) — `app.defaults.json` + secrets merge
- [cross-cutting/json-schemas/](./cross-cutting/json-schemas/)

## Pipeline stages

- [pipeline/capture/README.md](./pipeline/capture/README.md)
- [pipeline/audio_preclean/README.md](./pipeline/audio_preclean/README.md) — optional background-noise removal (DeepFilterNet)
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
- [workflows/stage-execution-reuse.md](./workflows/stage-execution-reuse.md) — reuse prior exec_* stage outputs (same source audio hash)
- [workflows/feedback-loops-and-reruns.md](./workflows/feedback-loops-and-reruns.md)
- [workflows/operator-stage-checklists.md](./workflows/operator-stage-checklists.md)
- [workflows/gui-surface-map.md](./workflows/gui-surface-map.md) — panels ↔ API ↔ logs ↔ artifacts (6 pipeline sub-tabs, status banner, session clear)
- [workflows/api-reference.md](./workflows/api-reference.md) — FastAPI `/api/*` routes, bodies, errors
- [workflows/long-interview-chunking.md](./workflows/long-interview-chunking.md) — context caps policy
- [workflows/troubleshooting.md](./workflows/troubleshooting.md)
- [workflows/smoke-test.md](./workflows/smoke-test.md)

## Builder and agent

- [../AGENTS.md](../AGENTS.md) — agent read order
- [build-out/implementation-guide.md](./build-out/implementation-guide.md) — master plan
- [build-out/remaining-build-commands.md](./build-out/remaining-build-commands.md) — remaining Agent commands
- [build-out/definition-of-done-signoff.md](./build-out/definition-of-done-signoff.md) — release-candidate checklist
- [build-out/full-application-flow.md](./build-out/full-application-flow.md) — end-to-end operator + system journey
- [build-out/stage-registry.md](./build-out/stage-registry.md) — every stage id, module, artifact, status
- [build-out/ticket-specs.md](./build-out/ticket-specs.md) — acceptance criteria per BUILD ticket
- [build-out/README.md](./build-out/README.md) — numbered tickets (Waves 0–7)
- [build-out/steps-forward.md](./build-out/steps-forward.md) — prioritized backlog + **Cursor Agent copy-paste prompts** (#0–#20)
- [build-out/repository-map.md](./build-out/repository-map.md) — repo layout ↔ modules ↔ docs
- [build-out/testing-and-verification.md](./build-out/testing-and-verification.md) — verify each wave
- [build-out/doc-maintenance.md](./build-out/doc-maintenance.md) — docs to update per PR

## R&D (optional, off default path)

- [pipeline/value-analysis/README.md](./pipeline/value-analysis/README.md)
- [build-out/gap-closure-agent-commands.md](./build-out/gap-closure-agent-commands.md) — historical
- [build-out/steps-forward.md](./build-out/steps-forward.md) — historical Agent prompts
