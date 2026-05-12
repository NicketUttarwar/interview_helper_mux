---
id: capability-matrix
tier: both
status: spec
depends_on: [version-low-risk, version-high-risk]
---

# Capability matrix (low vs high risk)

Rows are capabilities; columns summarize how each tier usually treats them. Tune per project.

| Capability | Low-risk | High-risk |
|------------|----------|-----------|
| **STT** | Single provider; one transcript artifact | Multi-provider, merge or vote; versioned transcripts |
| **Word timestamps** | Required if available from provider | Same + alignment repair across models |
| **Diarization** | Optional or off | Strong speaker clustering, overlap handling |
| **Segmentation** | Pauses / simple windows / light NLP | Embeddings, topic shifts, multi-candidate graphs |
| **Salience / “most detail”** | Heuristics + optional one LLM rank | Ensembles, re-score loops, diversity constraints |
| **Snippet store** | SQLite/JSON manifest | Same schema + richer provenance (model IDs, hashes) |
| **Audio cuts** | ffmpeg-style lossless regions | + separation, denoise, adaptive crossfades |
| **Assembly / mux** | Linear playlist + light crossfade | Dynamic EDL graph, branching inserts |
| **Mastering** | Target LUFS, simple limiter chain | Multi-bus, music beds, heavier processing |
| **Custom ML** | None | Fine-tune, S2S, proprietary APIs as needed |
| **Orchestration** | Fixed preset; minimal user input | Mostly automatic; prompts steer DAG ([../execution/automation-and-prompt-orchestration.md](../execution/automation-and-prompt-orchestration.md)) |
| **High-risk tool policy** | Optional API cost cap only | **First-use gate** per tool/version before new adapters run ([../execution/high-risk-first-use-gating.md](../execution/high-risk-first-use-gating.md)) |

## Failure modes to document per integration

- **Cost:** runaway minutes on streaming APIs.
- **Latency:** long jobs blocking human review.
- **Drift:** model updates changing segment boundaries—mitigate with [../workflows/idempotent-runs.md](../workflows/idempotent-runs.md).

## Open decisions

- Minimum bar for promoting a capability from “high only” to “low” over time.

## Links

- [low-risk.md](low-risk.md)
- [high-risk.md](high-risk.md)
- [../execution/README.md](../execution/README.md)
- [../cross-cutting/evaluation-metrics.md](../cross-cutting/evaluation-metrics.md)
