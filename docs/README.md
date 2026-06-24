# Documentation

Authoritative specs for **interview_helper_mux** — raw interview audio to three deliverables.

**Toolchain versions:** All dependency pins, vulnerability setup gate, and Context7 rules live in [cross-cutting/anchored-toolchain.md](./cross-cutting/anchored-toolchain.md). Do not duplicate version numbers in other docs — link there.

## Contents

| Document | Purpose |
|----------|---------|
| [INDEX.md](./INDEX.md) | Flat hub |
| [roadmap/future-proofing.md](./roadmap/future-proofing.md) | Future-proofing: guardrails + small R&D directions (audio-only) |
| [roadmap/README.md](./roadmap/README.md) | Roadmap folder pointer |
| [pipeline/value-analysis/README.md](./pipeline/value-analysis/README.md) | Optional: spike rubrics / moonshots (see future-proofing first) |
| [pipeline.md](./pipeline.md) | Pipeline, operator gates, three flows |
| [workflows/operator-flow-audit.md](./workflows/operator-flow-audit.md) | Full GUI tab/modal flows and resolved UX audit |
| [workflows/gui-flow-hardening.md](./workflows/gui-flow-hardening.md) | Operator feedback contract (toasts, spinners, checkpoints) |
| [logic-tree.md](./logic-tree.md) | Gap detection and decisions |
| [prompts/](./prompts/) | LLM system prompts |
| [cross-cutting/analysis-memory.md](./cross-cutting/analysis-memory.md) | Per-interview profile files |
| [cross-cutting/artifact-generation-and-validation.md](./cross-cutting/artifact-generation-and-validation.md) | Flagship LLM artifacts, gap-fill, schema + Zod validation |
| [cross-cutting/source-derived-sonic-mix-profile.md](./cross-cutting/source-derived-sonic-mix-profile.md) | Source-derived pacing/mix profile for cohesive SFX (shipped, BUILD-082) |
| [build-out/remaining-build-commands.md](./build-out/remaining-build-commands.md) | **Remaining** Agent commands (top-down backlog) |
| [build-out/definition-of-done-signoff.md](./build-out/definition-of-done-signoff.md) | Manual release-candidate checklist |
| [build-out/](./build-out/) | **Full build-out suite:** [implementation guide](./build-out/implementation-guide.md), [application flow](./build-out/full-application-flow.md), [stage registry](./build-out/stage-registry.md), [ticket specs](./build-out/ticket-specs.md), [tickets](./build-out/README.md), [steps forward](./build-out/steps-forward.md) (includes **Cursor Agent prompts**), [repository map](./build-out/repository-map.md) |
| [cross-cutting/](./cross-cutting/) | Schemas, artifacts, models |
| [cross-cutting/assets-and-executions.md](./cross-cutting/assets-and-executions.md) | ASSETS input picker, executions, resume after `run.sh` |
| [cross-cutting/anchored-toolchain.md](./cross-cutting/anchored-toolchain.md) | Pinned Python/system/API versions, anchor lock, `pip-audit`, Context7 |
| [cross-cutting/llm-orchestration.md](./cross-cutting/llm-orchestration.md) | Smart LLM routing: arbiter, tiers, shard/collate (BUILD-073) |
| [cross-cutting/llm-stage-model-matrix.md](./cross-cutting/llm-stage-model-matrix.md) | Per-stage model tier matrix |
| [cross-cutting/local-audio-stack.md](./cross-cutting/local-audio-stack.md) | local MMAudio SFX + isolation + GUI journey |
| [cross-cutting/local-audio-stack.md](./cross-cutting/local-audio-stack.md) | `prompt_influence` tuning table |
| [prompts/_shared/examples/sfx-prompt-regression.md](./prompts/_shared/examples/sfx-prompt-regression.md) | Golden prompt regression QA |
| [cross-cutting/json-schema-coverage.md](./cross-cutting/json-schema-coverage.md) | Schema coverage gaps + resilient guards |
| [cross-cutting/config-keys.md](./cross-cutting/config-keys.md) | `app.defaults.json` + secrets keys reference |
| [workflows/](./workflows/) | Gates, idempotency, stage reuse, smoke test |
| [workflows/stage-execution-reuse.md](./workflows/stage-execution-reuse.md) | Per-stage reuse from prior executions (source audio hash match) |
| [workflows/gui-surface-map.md](./workflows/gui-surface-map.md) | GUI panels ↔ API ↔ logs ↔ artifacts |
| [workflows/api-reference.md](./workflows/api-reference.md) | HTTP `/api/*` reference (methods, bodies, errors) |
| [workflows/long-interview-chunking.md](./workflows/long-interview-chunking.md) | Context caps + chunking policy |
| [workflows/operator-stage-checklists.md](./workflows/operator-stage-checklists.md) | Per-stage operator verification |
| [workflows/troubleshooting.md](./workflows/troubleshooting.md) | Symptom playbook + guards |
| [workflows/smoke-test.md](./workflows/smoke-test.md) | Greenfield machine checklist |
| [pipeline/transcription/transcript-review.md](./pipeline/transcription/transcript-review.md) | G0 operator STT QC — synced dock, fuzzy similar-word replace |
| [pipeline/transcription/stt-and-diarization.md](./pipeline/transcription/stt-and-diarization.md) | STT + diarization options (catalog) |
| [pipeline/transcription/source-separation-and-enhancement.md](./pipeline/transcription/source-separation-and-enhancement.md) | Denoise / separation options |

## Inputs and outputs

- **Input:** Raw interview audio under `./ASSETS/` — pick a file in the GUI home screen; no config path required ([cross-cutting/assets-and-executions.md](./cross-cutting/assets-and-executions.md))
- **Run state:** Each execution under `ASSETS/executions/exec_NNN_<hash12>_TIMESTAMP` — resume after relaunching `./scripts/run.sh`; hash enables per-stage reuse from prior runs on the same WAV
- **Quality (optional, two moments):** [Background noise removal](./pipeline/audio_preclean/README.md) — before ingest and **after recording pickup questions at G1**
- **Outputs (per run, operator chooses one flow after analysis):**
  1. **Full master podcast** — full coverage, optimal order, VO bridges, podcast SFX, mastered WAV
  2. **Highlight reel** — ≤5 clips, montage SFX, mastered WAV
  3. **Podcast show description** — ~200-word, third-person blurb to entice listeners (text; no audio mux)

Shared stages run first via `tools/run_analysis.py`. Flow work runs via `tools/run_flow.py`.

**Implementation status:** Shared analysis, Flow 1/2 mix (`mix_flow1` / `mix_flow2` — VO + SFX in `master.wav`), Flow 3 publishing, and `source_acoustic_profile` (BUILD-082) are shipped. Stage ids: [stage-registry.md](./build-out/stage-registry.md). Release sign-off: [definition-of-done-signoff.md](./build-out/definition-of-done-signoff.md). Remaining quality work: [podcast-quality-roadmap.md](./cross-cutting/podcast-quality-roadmap.md) · [build-out/README.md](./build-out/README.md).
