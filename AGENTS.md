# Agent guide — interview_helper_mux

**Persistent constraints** (logging, gates, toolchain, build-out workflow, v1 honesty, doc obligations) live in **`.cursor/rules/interview-helper-mux.mdc`** — always applied in Cursor. This file is the **navigation index** into `docs/`.

## Read order

1. [docs/roadmap/future-proofing.md](docs/roadmap/future-proofing.md) — guardrails + optional R&D (audio-only)
2. [docs/build-out/implementation-guide.md](docs/build-out/implementation-guide.md) — full-repository build plan (all phases)
3. [docs/build-out/remaining-build-commands.md](docs/build-out/remaining-build-commands.md) — **remaining** Agent commands (top-down; no shipped BUILD repeats)
4. [docs/build-out/gap-closure-agent-commands.md](docs/build-out/gap-closure-agent-commands.md) — gap-closure Agent queue (GC-00–GC-D1 shipped; Phase 6 follow-up)
5. [docs/build-out/steps-forward.md](docs/build-out/steps-forward.md) — full backlog + historical Agent prompts (#0–#20)
6. [docs/build-out/ticket-specs.md](docs/build-out/ticket-specs.md) — acceptance criteria for your BUILD ticket(s)
7. [docs/build-out/stage-registry.md](docs/build-out/stage-registry.md) — stage id ↔ module ↔ artifacts
8. [docs/workflows/operator-journey.md](docs/workflows/operator-journey.md) — **operator** happy path (Prepare → Ship; journey kernel)
8b. [docs/workflows/operator-flow-audit.md](docs/workflows/operator-flow-audit.md) — full GUI tab/modal flow map + resolved UX issues
9. [docs/build-out/full-application-flow.md](docs/build-out/full-application-flow.md) — end-to-end system + CLI journey
10. [docs/build-out/repository-map.md](docs/build-out/repository-map.md) — repo layout ↔ code ↔ docs
11. [docs/build-out/README.md](docs/build-out/README.md) — ticket index (Waves 0–7)
12. [docs/cross-cutting/podcast-quality-roadmap.md](docs/cross-cutting/podcast-quality-roadmap.md) — v1 vs target master
13. [docs/workflows/operator-gates.md](docs/workflows/operator-gates.md) — gates + quality offers
12. [docs/workflows/operator-stage-checklists.md](docs/workflows/operator-stage-checklists.md) — per-stage verification (extend when you add stages)
13. [docs/workflows/gui-surface-map.md](docs/workflows/gui-surface-map.md) — GUI ↔ API ↔ logs ↔ artifacts
14. [docs/workflows/api-reference.md](docs/workflows/api-reference.md) — `/api/*` contract
14b. [docs/workflows/stage-execution-reuse.md](docs/workflows/stage-execution-reuse.md) — reuse prior exec_* stage outputs (same source audio hash)
14c. Write approval — `journey_ui.require_write_approval_per_stage`; `.pending_writes/` — [gui-surface-map.md](docs/workflows/gui-surface-map.md), [api-reference.md](docs/workflows/api-reference.md)
15. [docs/pipeline.md](docs/pipeline.md) — three flows, stage overview
16. [docs/cross-cutting/artifact-layout.md](docs/cross-cutting/artifact-layout.md) — paths per run
16b. [docs/cross-cutting/artifact-generation-and-validation.md](docs/cross-cutting/artifact-generation-and-validation.md) — flagship LLM artifacts, gap-fill, JSON Schema + Zod
16c. [LLM-ANALYSIS-ARCHITECTURE.md](LLM-ANALYSIS-ARCHITECTURE.md) — LLM volley, routing, disk outputs; **§18 Flow hardening** (completion truth, preflight, cross-validate)
17. [docs/cross-cutting/config-keys.md](docs/cross-cutting/config-keys.md) — defaults + secrets keys
18. [docs/build-out/doc-maintenance.md](docs/build-out/doc-maintenance.md) — docs to update per PR
19. [docs/build-out/testing-and-verification.md](docs/build-out/testing-and-verification.md) — verify each wave
20. [docs/build-out/definition-of-done-signoff.md](docs/build-out/definition-of-done-signoff.md) — manual release-candidate checklist (ASSETS, G2×3 flows, mix listen, pre-clean, parity)

## Audio / STT / ElevenLabs (when implementing those areas)

- [docs/pipeline/transcription/transcript-review.md](docs/pipeline/transcription/transcript-review.md) — G0 gate, synced dock word editor, fuzzy similar-word replace
- [docs/pipeline/transcription/disfluency-extract.md](docs/pipeline/transcription/disfluency-extract.md) — G0.5 filler extract/review; `disfluency_catalog` in LLM stages
- [docs/pipeline/assembly_and_mux/disfluency-restore.md](docs/pipeline/assembly_and_mux/disfluency-restore.md) — EDL/mix restore
- [docs/pipeline/transcription/stt-and-diarization.md](docs/pipeline/transcription/stt-and-diarization.md)
- [docs/pipeline/transcription/source-separation-and-enhancement.md](docs/pipeline/transcription/source-separation-and-enhancement.md)
- [docs/cross-cutting/elevenlabs-integration-guide.md](docs/cross-cutting/elevenlabs-integration-guide.md)
- [docs/cross-cutting/elevenlabs-prompt-influence-tuning.md](docs/cross-cutting/elevenlabs-prompt-influence-tuning.md)
- [docs/prompts/_shared/examples/elevenlabs-prompt-regression.md](docs/prompts/_shared/examples/elevenlabs-prompt-regression.md)

## LLM call records (audit / copy-paste)

- [docs/cross-cutting/llm-call-record-framework.md](docs/cross-cutting/llm-call-record-framework.md) — labels, paths, volley reconstruction
- `python tools/export_llm_calls.py --run-id <exec_*>` — export markdown/jsonl for review

## Local LLM (default on; `local_llm.enabled`)

- [docs/cross-cutting/local-llm-tier.md](docs/cross-cutting/local-llm-tier.md) — MLX volley framing before OpenAI; fail-safe escalation
- [docs/cross-cutting/local-llm-implementation-handoff.md](docs/cross-cutting/local-llm-implementation-handoff.md) — implementation checklist
- `python scripts/select_local_llm.py --download` — llmfit hardware pick + weights under `ASSETS/local_llm/models/`

## Building code in Cursor

Optional: automate markdown command queues with [CURSOR_EXECUTE/README.md](CURSOR_EXECUTE/README.md) (`./CURSOR_EXECUTE/run.sh <commands.md>`).

1. Open **Agent mode** (not Ask).
2. Pick the next command in [docs/build-out/remaining-build-commands.md](docs/build-out/remaining-build-commands.md) (or historical steps in [steps-forward.md](docs/build-out/steps-forward.md)).
3. Copy the **Agent prompt** for that step into chat; `@`-attach the listed docs.
4. Run the step **Verify** shell block when the agent finishes.

## Testing (quick)

See **Verify before finishing** in `.cursor/rules/interview-helper-mux.mdc`, per-step blocks in [docs/build-out/steps-forward.md](docs/build-out/steps-forward.md), [docs/workflows/smoke-test.md](docs/workflows/smoke-test.md), and [docs/build-out/definition-of-done-signoff.md](docs/build-out/definition-of-done-signoff.md) for release sign-off.
