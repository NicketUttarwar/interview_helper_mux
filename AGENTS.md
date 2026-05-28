# Agent guide — interview_helper_mux

**Persistent constraints** (logging, gates, toolchain, build-out workflow, v1 honesty, doc obligations) live in **`.cursor/rules/interview-helper-mux.mdc`** — always applied in Cursor. This file is the **navigation index** into `docs/`.

## Read order

1. [docs/roadmap/future-proofing.md](docs/roadmap/future-proofing.md) — guardrails + optional R&D (audio-only)
2. [docs/build-out/implementation-guide.md](docs/build-out/implementation-guide.md) — full-repository build plan (all phases)
3. [docs/build-out/steps-forward.md](docs/build-out/steps-forward.md) — prioritized backlog + **copy-paste Cursor Agent prompts** per step (#0–#20)
4. [docs/build-out/ticket-specs.md](docs/build-out/ticket-specs.md) — acceptance criteria for your BUILD ticket(s)
5. [docs/build-out/stage-registry.md](docs/build-out/stage-registry.md) — stage id ↔ module ↔ artifacts
6. [docs/build-out/full-application-flow.md](docs/build-out/full-application-flow.md) — end-to-end operator + system journey
7. [docs/build-out/repository-map.md](docs/build-out/repository-map.md) — repo layout ↔ code ↔ **known doc↔code gaps**
8. [docs/build-out/README.md](docs/build-out/README.md) — ticket index (Waves 0–7)
9. [docs/cross-cutting/podcast-quality-roadmap.md](docs/cross-cutting/podcast-quality-roadmap.md) — v1 vs target master
10. [docs/workflows/operator-gates.md](docs/workflows/operator-gates.md) — gates + quality offers
11. [docs/workflows/operator-stage-checklists.md](docs/workflows/operator-stage-checklists.md) — per-stage verification (extend when you add stages)
12. [docs/workflows/gui-surface-map.md](docs/workflows/gui-surface-map.md) — GUI ↔ API ↔ logs ↔ artifacts
13. [docs/workflows/api-reference.md](docs/workflows/api-reference.md) — `/api/*` contract
14. [docs/pipeline.md](docs/pipeline.md) — three flows, stage overview
15. [docs/cross-cutting/artifact-layout.md](docs/cross-cutting/artifact-layout.md) — paths per run
16. [docs/cross-cutting/config-keys.md](docs/cross-cutting/config-keys.md) — defaults + secrets keys
17. [docs/build-out/doc-maintenance.md](docs/build-out/doc-maintenance.md) — docs to update per PR
18. [docs/build-out/testing-and-verification.md](docs/build-out/testing-and-verification.md) — verify each wave

## Audio / STT / ElevenLabs (when implementing those areas)

- [docs/pipeline/transcription/stt-and-diarization.md](docs/pipeline/transcription/stt-and-diarization.md)
- [docs/pipeline/transcription/source-separation-and-enhancement.md](docs/pipeline/transcription/source-separation-and-enhancement.md)
- [docs/cross-cutting/elevenlabs-integration-guide.md](docs/cross-cutting/elevenlabs-integration-guide.md)
- [docs/cross-cutting/elevenlabs-prompt-influence-tuning.md](docs/cross-cutting/elevenlabs-prompt-influence-tuning.md)
- [docs/prompts/_shared/examples/elevenlabs-prompt-regression.md](docs/prompts/_shared/examples/elevenlabs-prompt-regression.md)

## Building code in Cursor

1. Open **Agent mode** (not Ask).
2. Pick the next step in [docs/build-out/steps-forward.md](docs/build-out/steps-forward.md) (section **Cursor Agent**).
3. Copy the **Agent prompt** for that step into chat; `@`-attach the listed docs.
4. Run the step **Verify** shell block when the agent finishes.

## Testing (quick)

See **Verify before finishing** in `.cursor/rules/interview-helper-mux.mdc`, per-step blocks in [docs/build-out/steps-forward.md](docs/build-out/steps-forward.md), and [docs/workflows/smoke-test.md](docs/workflows/smoke-test.md).
