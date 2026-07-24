# Documentation index

Hub for **interview_helper_mux v2** — one interview → `master/master.wav`.

## Operator (start here)

- [workflows/operator-journey.md](./workflows/operator-journey.md) — 10-phase happy path (Prepare → Ship)
- [workflows/operator-gates.md](./workflows/operator-gates.md) — G0, optional G1, preclean offer
- [workflows/operator-sound-and-mix.md](./workflows/operator-sound-and-mix.md) — SAP → SDP → MMAudio → mix
- [workflows/troubleshooting.md](./workflows/troubleshooting.md)
- [workflows/smoke-test.md](./workflows/smoke-test.md)
- [cross-cutting/assets-and-executions.md](./cross-cutting/assets-and-executions.md)
- [v2/port-manifest.csv](./v2/port-manifest.csv) — 32 stage inventory

## Core specs

- [README.md](./README.md) — doc overview
- [pipeline.md](./pipeline.md) — stage graph
- [prompts/README.md](./prompts/README.md) — LLM prompt tree
- [prompts/sound_design/README.md](./prompts/sound_design/README.md) — sound-design LLM + MMAudio

## Cross-cutting

- [cross-cutting/anchored-toolchain.md](./cross-cutting/anchored-toolchain.md) — pinned deps, CVE gate
- [cross-cutting/local-audio-stack.md](./cross-cutting/local-audio-stack.md) — DeepFilterNet + MMAudio + CLAP
- [cross-cutting/speech-to-speech-vo.md](./cross-cutting/speech-to-speech-vo.md) — S2S gap VO (R&D): synthesis, VC, prosody, tone
- [cross-cutting/chatterbox-interviewer-vo.md](./cross-cutting/chatterbox-interviewer-vo.md) — Chatterbox zero-shot gap VO + degradation ladder
- [cross-cutting/reliability-charter.md](./cross-cutting/reliability-charter.md) — holistic guardrails, QC tiers, config index
- [cross-cutting/volley-glossary.md](./cross-cutting/volley-glossary.md) — **speaker volley** vs **LLM volley**
- [cross-cutting/volley-inventory.md](./cross-cutting/volley-inventory.md) — repo sweep classes + new modules
- [cross-cutting/stage-volley-matrix.md](./cross-cutting/stage-volley-matrix.md) — every stage ↔ volley relation
- [cross-cutting/episode-architecture-spine.md](./cross-cutting/episode-architecture-spine.md) — cold open → speaker volleys → master
- [cross-cutting/mix-house-chain.md](./cross-cutting/mix-house-chain.md) — mix order policy
- [cross-cutting/config-keys.md](./cross-cutting/config-keys.md) — `app.defaults.json`
- [cross-cutting/artifact-layout.md](./cross-cutting/artifact-layout.md)
- [cross-cutting/artifact-generation-and-validation.md](./cross-cutting/artifact-generation-and-validation.md)
- [cross-cutting/analysis-memory.md](./cross-cutting/analysis-memory.md)
- [cross-cutting/interview-spine.md](./cross-cutting/interview-spine.md)
- [cross-cutting/model-routing.md](./cross-cutting/model-routing.md)
- [workflows/api-reference.md](./workflows/api-reference.md)
- [workflows/gui-surface-map.md](./workflows/gui-surface-map.md)

## Pipeline stages

- [pipeline/capture/README.md](./pipeline/capture/README.md)
- [pipeline/audio_preclean/README.md](./pipeline/audio_preclean/README.md)
- [pipeline/ingest/README.md](./pipeline/ingest/README.md)
- [pipeline/transcription/README.md](./pipeline/transcription/README.md)
- [pipeline/understanding/README.md](./pipeline/understanding/README.md)
- [pipeline/segmentation/README.md](./pipeline/segmentation/README.md)
- [pipeline/interviewer-gap/README.md](./pipeline/interviewer-gap/README.md)
- [pipeline/scoring_and_selection/README.md](./pipeline/scoring_and_selection/README.md)
- [pipeline/audio_editing/README.md](./pipeline/audio_editing/README.md)
- [pipeline/assembly_and_mux/README.md](./pipeline/assembly_and_mux/README.md)
