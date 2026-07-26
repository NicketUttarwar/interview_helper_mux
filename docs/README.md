# Documentation

Authoritative specs for **interview_helper_mux** — raw interview audio to one deliverable, `master/master.wav`.

**Toolchain versions:** All dependency pins, vulnerability setup gate, and Context7 rules live in [cross-cutting/anchored-toolchain.md](./cross-cutting/anchored-toolchain.md). Do not duplicate version numbers in other docs — link there.

## Contents

| Document | Purpose |
|----------|---------|
| [INDEX.md](./INDEX.md) | Flat hub |
| [roadmap/future-proofing.md](./roadmap/future-proofing.md) | Future-proofing: guardrails + small R&D directions (audio-only) |
| [roadmap/README.md](./roadmap/README.md) | Roadmap folder pointer |
| [pipeline/value-analysis/README.md](./pipeline/value-analysis/README.md) | Optional: spike rubrics / moonshots (see future-proofing first) |
| [v2/drop-manifest.md](./v2/drop-manifest.md) | What was removed from pre-v2 and must not be treated as live |
| [v2/port-manifest.csv](./v2/port-manifest.csv) | Stage-by-stage port status |
| [pipeline.md](./pipeline.md) | Pipeline and operator gates |
| [logic-tree.md](./logic-tree.md) | Gap detection and decisions |
| [prompts/](./prompts/) | LLM system prompts |
| [cross-cutting/analysis-memory.md](./cross-cutting/analysis-memory.md) | Per-interview profile files |
| [cross-cutting/artifact-generation-and-validation.md](./cross-cutting/artifact-generation-and-validation.md) | Flagship LLM artifacts, gap-fill, schema + Zod validation |
| [cross-cutting/source-derived-sonic-mix-profile.md](./cross-cutting/source-derived-sonic-mix-profile.md) | Source-derived pacing/mix profile for cohesive SFX (shipped, BUILD-082) |
| [cross-cutting/](./cross-cutting/) | Schemas, artifacts, models |
| [cross-cutting/assets-and-executions.md](./cross-cutting/assets-and-executions.md) | ASSETS input picker, executions, resume after `run.sh` |
| [cross-cutting/anchored-toolchain.md](./cross-cutting/anchored-toolchain.md) | Pinned Python/system/API versions, anchor lock, `pip-audit`, Context7 |
| [cross-cutting/llm-stage-model-matrix.md](./cross-cutting/llm-stage-model-matrix.md) | Per-stage model tier matrix |
| [cross-cutting/local-audio-stack.md](./cross-cutting/local-audio-stack.md) | Local DeepFilterNet + MMAudio stacks, isolation, MMAudio prompt tuning |
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
- **Output:** one **full master podcast** per run — `master/master.wav`: full coverage, optimal order, VO bridges, podcast SFX, mastered WAV

There is a single delivery path. The highlight-reel and show-description flows (Flow 2 / Flow 3) and the G2 flow picker were removed — see [v2/drop-manifest.md](./v2/drop-manifest.md).

Analysis runs via `tools/run_analysis.py`, delivery via `tools/run_delivery.py`. Canonical stage ids: [`src/interview_mux/v2/config.py`](../src/interview_mux/v2/config.py) and [v2/port-manifest.csv](./v2/port-manifest.csv). Remaining quality work: [podcast-quality-roadmap.md](./cross-cutting/podcast-quality-roadmap.md).
