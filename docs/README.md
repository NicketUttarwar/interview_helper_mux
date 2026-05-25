# Documentation

Authoritative specs for **interview_helper_mux** — raw interview audio to two deliverables.

## Contents

| Document | Purpose |
|----------|---------|
| [INDEX.md](./INDEX.md) | Flat hub |
| [pipeline.md](./pipeline.md) | Pipeline, operator gates, two flows |
| [logic-tree.md](./logic-tree.md) | Gap detection and decisions |
| [prompts/](./prompts/) | LLM system prompts |
| [cross-cutting/analysis-memory.md](./cross-cutting/analysis-memory.md) | Per-interview profile files |
| [build-out/](./build-out/) | Agent implementation tickets |
| [cross-cutting/](./cross-cutting/) | Schemas, artifacts, models |
| [workflows/](./workflows/) | Gates, idempotency, smoke test |

## Inputs and outputs

- **Input:** Raw interview audio under `./ASSETS/`
- **Quality (optional, offered throughout):** [Background noise removal](./pipeline/audio_preclean/README.md) — before ingest, after transcript review, **after recording pickup questions at G1**, and before final mix
- **Outputs (per run, operator chooses one flow after analysis):**
  1. **Full master podcast** — full coverage, optimal order, VO bridges, podcast SFX, mastered WAV
  2. **Highlight reel** — ≤5 clips, montage SFX, mastered WAV

Shared stages run first via `tools/run_analysis.py`. Flow work runs via `tools/run_flow.py`.

**Implementation status:** Analysis and selection are largely implemented; full podcast mix (VO + SFX + beds in `master.wav`) is specified in [podcast-quality-roadmap.md](./cross-cutting/podcast-quality-roadmap.md) and [build-out/README.md](./build-out/README.md). v1 Flow 1 export is reordered speech until Wave 5 / assembly wiring ships.
