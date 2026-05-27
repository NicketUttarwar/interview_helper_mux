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
| [logic-tree.md](./logic-tree.md) | Gap detection and decisions |
| [prompts/](./prompts/) | LLM system prompts |
| [cross-cutting/analysis-memory.md](./cross-cutting/analysis-memory.md) | Per-interview profile files |
| [cross-cutting/source-derived-sonic-mix-profile.md](./cross-cutting/source-derived-sonic-mix-profile.md) | Source-derived pacing/mix profile for cohesive SFX (planned) |
| [build-out/](./build-out/) | Tickets, [repository map](./build-out/repository-map.md), [steps forward](./build-out/steps-forward.md) |
| [cross-cutting/](./cross-cutting/) | Schemas, artifacts, models |
| [cross-cutting/anchored-toolchain.md](./cross-cutting/anchored-toolchain.md) | Pinned Python/system/API versions, anchor lock, `pip-audit`, Context7 |
| [cross-cutting/llm-orchestration.md](./cross-cutting/llm-orchestration.md) | Smart LLM routing: arbiter, tiers, shard/collate (**spec**) |
| [cross-cutting/llm-stage-model-matrix.md](./cross-cutting/llm-stage-model-matrix.md) | Per-stage model tier matrix |
| [cross-cutting/elevenlabs-integration-guide.md](./cross-cutting/elevenlabs-integration-guide.md) | ElevenLabs REST SFX + isolation + GUI journey |
| [cross-cutting/elevenlabs-prompt-influence-tuning.md](./cross-cutting/elevenlabs-prompt-influence-tuning.md) | `prompt_influence` tuning table |
| [prompts/_shared/examples/elevenlabs-prompt-regression.md](./prompts/_shared/examples/elevenlabs-prompt-regression.md) | Golden prompt regression QA |
| [cross-cutting/json-schema-coverage.md](./cross-cutting/json-schema-coverage.md) | Schema coverage gaps + resilient guards |
| [cross-cutting/config-keys.md](./cross-cutting/config-keys.md) | `app.defaults.json` + secrets keys reference |
| [workflows/](./workflows/) | Gates, idempotency, smoke test |
| [workflows/gui-surface-map.md](./workflows/gui-surface-map.md) | GUI panels ↔ API ↔ logs ↔ artifacts |
| [workflows/api-reference.md](./workflows/api-reference.md) | HTTP `/api/*` reference (methods, bodies, errors) |
| [workflows/long-interview-chunking.md](./workflows/long-interview-chunking.md) | Context caps + chunking policy |
| [workflows/operator-stage-checklists.md](./workflows/operator-stage-checklists.md) | Per-stage operator verification |
| [workflows/troubleshooting.md](./workflows/troubleshooting.md) | Symptom playbook + guards |
| [workflows/smoke-test.md](./workflows/smoke-test.md) | Greenfield machine checklist |
| [pipeline/transcription/stt-and-diarization.md](./pipeline/transcription/stt-and-diarization.md) | STT + diarization options (catalog) |
| [pipeline/transcription/source-separation-and-enhancement.md](./pipeline/transcription/source-separation-and-enhancement.md) | Denoise / separation options |

## Inputs and outputs

- **Input:** Raw interview audio under `./ASSETS/`
- **Quality (optional, offered throughout):** [Background noise removal](./pipeline/audio_preclean/README.md) — before ingest, after transcript review, **after recording pickup questions at G1**, and before final mix
- **Outputs (per run, operator chooses one flow after analysis):**
  1. **Full master podcast** — full coverage, optimal order, VO bridges, podcast SFX, mastered WAV
  2. **Highlight reel** — ≤5 clips, montage SFX, mastered WAV
  3. **Podcast show description** — ~200-word, third-person blurb to entice listeners (text; no audio mux)

Shared stages run first via `tools/run_analysis.py`. Flow work runs via `tools/run_flow.py`.

**Implementation status:** Analysis and selection are largely implemented; full podcast mix (VO + SFX + beds in `master.wav`) is specified in [podcast-quality-roadmap.md](./cross-cutting/podcast-quality-roadmap.md) and [build-out/README.md](./build-out/README.md). v1 Flow 1 export is reordered speech until Wave 5 / assembly wiring ships.
