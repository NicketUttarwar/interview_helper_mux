# Value analysis (optional detail)

Spike rubrics, moonshots, and scratch notes for **future-proofing** — see [guardrails first](../../roadmap/future-proofing.md). Any spike that adds libraries must pin versions in [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md) and pass `pip-audit`.

| Doc | Purpose |
|-----|---------|
| [phase3-spike-framework.md](./phase3-spike-framework.md) | How to score R&D candidates (LEX / COM / CRE) |
| [value-metrics-library.md](./value-metrics-library.md) | Human + proxy metric definitions |
| [moonshot-model-families.md](./moonshot-model-families.md) | Audio-only model families (SSL, CLAP, …) |
| [tools-not-in-repo-landscape.md](./tools-not-in-repo-landscape.md) | Tools by value lever |
| [spike-results-and-winners.md](./spike-results-and-winners.md) | Outcomes after spikes |
| [spike-score-templates/](./spike-score-templates/) | Blank score sheets |

Per-stage notes (if needed): [sections/](./sections/).

---

## Tooling (feature-flagged)

Deterministic extract + spike CLIs — **not** registered as separate stages in [`pipeline.py`](../../src/interview_mux/pipeline.py). Shipped defaults in `config/app.defaults.json` have the master switch and auto-extract **on**; see [config-keys.md](../../cross-cutting/config-keys.md).

**Execution guide:** [g15-and-value-analysis-execution.md](../../build-out/g15-and-value-analysis-execution.md) (Track B commands, file checklist).

| Flag | Default | Effect |
|------|---------|--------|
| `value_analysis.enabled` | `true` | Master switch; when `false`, CLIs exit 0 with a message |
| `value_analysis.spike_scoring` | `true` | Allows `tools/run_value_spike.py` when master is on |
| `value_analysis.transcript_features` | `true` | Transcript profile in `extract_value_features` |
| `value_analysis.audio_features` | `true` | Audio profile (`ingest/normalized.wav`) in extractor |
| `value_analysis.auto_extract_after_content_context` | `true` | After successful `content_context`, write `understanding/value_features.json` when master + this flag on |

**Spike scoring** — aggregate scorecard JSON (LEX / COM / CRE rubric):

```bash
python tools/run_value_spike.py \
  --scorecard tests/fixtures/value_analysis/spike_flow1_sound.json \
  --profiles listener-first,idea-first \
  --out /tmp/spike_ranked.json
```

**Feature extraction** — merge profiles into `understanding/value_features.json` ([schema](../../cross-cutting/json-schemas/value_features.schema.json)):

```bash
python tools/extract_value_features.py --run-id exec_001_a1b2c3d4e5f6_20260523T120000Z --profile all
python tools/extract_value_features.py --run-id exec_001_a1b2c3d4e5f6_20260523T120000Z --profile transcript
```

Module: `src/interview_mux/value_analysis/extract.py` (`extract_and_write_value_features`, `maybe_auto_extract_value_features`).

With shipped defaults, a normal `content_context` run also writes the artifact (no separate CLI). Set either flag to `false` in `config/app.defaults.json` to disable.

Record spike outcomes in [spike-results-and-winners.md](./spike-results-and-winners.md).

---

## Build-out

Auto-extract and enrichment signals are on the default analysis path when flags are on. Moonshot spikes (SSL, CLAP, etc.) remain optional R&D: [steps-forward.md](../../build-out/steps-forward.md) · [future-proofing.md](../../roadmap/future-proofing.md).
