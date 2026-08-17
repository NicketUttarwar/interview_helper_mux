# Documentation index

Hub for **interview_helper_mux v2** — one messy interview → structured `master/master.wav` (golden nuggets, ideal cuts, native↔synthetic↔sonic conversation). Product Essence and **authoritative listen-delight** ship gate: [NORTH_STAR.md](../NORTH_STAR.md).

## Operator (start here)

- [workflows/operator-journey.md](./workflows/operator-journey.md) — 10-phase happy path (Prepare → Ship)
- [workflows/operator-gates.md](./workflows/operator-gates.md) — G0, optional G1, preclean offer
- [workflows/operator-sound-and-mix.md](./workflows/operator-sound-and-mix.md) — SAP → SDP → MMAudio → mix
- [workflows/troubleshooting.md](./workflows/troubleshooting.md)
- [workflows/smoke-test.md](./workflows/smoke-test.md)
- [cross-cutting/assets-and-executions.md](./cross-cutting/assets-and-executions.md)
- [v2/port-manifest.csv](./v2/port-manifest.csv) — 65-stage inventory + gates (incl. Mastering research/Shape, air-script, Refinement Pass, G-Publish)

## Core specs

- [README.md](./README.md) — doc overview
- [pipeline.md](./pipeline.md) — stage graph
- [prompts/README.md](./prompts/README.md) — LLM prompt tree
- [prompts/sound_design/README.md](./prompts/sound_design/README.md) — sound-design LLM + MMAudio

## Cross-cutting

- [cross-cutting/mastering-process.md](./cross-cutting/mastering-process.md) — **Unified Mastering Process** (research → Shape Engine → realization)
- [cross-cutting/mastering-homunculus.md](./cross-cutting/mastering-homunculus.md) — **0.0.0 original vs 0.1.0 homunculus** (Start-tab brain slider)
- [cross-cutting/air-script.md](./cross-cutting/air-script.md) — Shape realization paper-edit on `mastering_plan` (beats, omits, sonic scenes)
- [cross-cutting/mastering-research-fields.md](./cross-cutting/mastering-research-fields.md) — 38 research fields + user-flow matrix
- [cross-cutting/mastering-shape-engine.md](./cross-cutting/mastering-shape-engine.md) — L0–L5, prompt edit, excellence filter
- [cross-cutting/mastering-construction-decisions.md](./cross-cutting/mastering-construction-decisions.md) — cold open + all construction decisions
- [cross-cutting/mastering-quality-hardening.md](./cross-cutting/mastering-quality-hardening.md) — **hardening layer** (routing, diversity, feasibility, integrity, Pareto)
- [cross-cutting/mastering-audition-loop.md](./cross-cutting/mastering-audition-loop.md) — micro-render auditions + closed-loop polish
- [cross-cutting/mastering-multi-critic.md](./cross-cutting/mastering-multi-critic.md) — six-critic L4 panel + flagship arbiter
- [cross-cutting/mastering-feasibility.md](./cross-cutting/mastering-feasibility.md) — deterministic plan feasibility checks
- [cross-cutting/mastering-semantic-integrity.md](./cross-cutting/mastering-semantic-integrity.md) — anti-misquote / chronology / false-reaction
- [cross-cutting/mastering-voice-clone-policy.md](./cross-cutting/mastering-voice-clone-policy.md) — clone consent, scope, disclosure, audit
- [cross-cutting/mastering-eval-corpus.md](./cross-cutting/mastering-eval-corpus.md) — fixture taxonomy + quality metrics
- [cross-cutting/mastering-integration-backlog.md](./cross-cutting/mastering-integration-backlog.md) — TBIY → mastering migration backlog
- [cross-cutting/refinement-passes.md](./cross-cutting/refinement-passes.md) — Refinement Pass: L0 agenda, L1 gate, CFI ledger, flow integrity
- [cross-cutting/tbiy-production-profile.md](./cross-cutting/tbiy-production-profile.md) — TBIY heritage (superseded as strategy)
- [cross-cutting/anchored-toolchain.md](./cross-cutting/anchored-toolchain.md) — pinned deps, CVE gate (AWS = Terraform + boto3, never AWS CLI)
- [cross-cutting/local-audio-stack.md](./cross-cutting/local-audio-stack.md) — DeepFilterNet + MMAudio + CLAP
- [cross-cutting/podcast-rss-hosting.md](./cross-cutting/podcast-rss-hosting.md) — The War Room S3 + CloudFront RSS (Terraform state + boto3 publish)
- [../terraform/README.md](../terraform/README.md) — Terraform wrappers, committed state, session backup
- [cross-cutting/podcast-cover-theme.md](./cross-cutting/podcast-cover-theme.md) — OpenAI cover theme (3-candidate brilliance pick)
- [cross-cutting/vernacular-evidence-covenant.md](./cross-cutting/vernacular-evidence-covenant.md) — audio probe platform + vernacular must_keep
- [cross-cutting/multilingual-support.md](./cross-cutting/multilingual-support.md) — same-language master plan (broader)
- [cross-cutting/speech-to-speech-vo.md](./cross-cutting/speech-to-speech-vo.md) — S2S gap VO (R&D): synthesis, VC, prosody, tone
- [cross-cutting/chatterbox-interviewer-vo.md](./cross-cutting/chatterbox-interviewer-vo.md) — Chatterbox zero-shot gap VO + degradation ladder
- [cross-cutting/reliability-charter.md](./cross-cutting/reliability-charter.md) — holistic guardrails, QC tiers, config index
- [cross-cutting/volley-glossary.md](./cross-cutting/volley-glossary.md) — **speaker volley** vs **LLM volley**
- [cross-cutting/volley-inventory.md](./cross-cutting/volley-inventory.md) — repo sweep classes + new modules
- [cross-cutting/stage-volley-matrix.md](./cross-cutting/stage-volley-matrix.md) — every stage ↔ volley relation
- [cross-cutting/episode-architecture-spine.md](./cross-cutting/episode-architecture-spine.md) — candidate spine under Mastering Process
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
- [pipeline/mastering_and_export/README.md](./pipeline/mastering_and_export/README.md)
- [pipeline/publishing/README.md](./pipeline/publishing/README.md) — G-Publish local package + S3 sync
