---
id: version-low-risk
tier: low
status: spec
depends_on: []
---

# Low-risk product tier

Default path when you want **predictable cost**, **few moving parts**, and **no custom training**.

## Goals

- One primary **speech-to-text** path (cloud STT or hosted Whisper-class API).
- **Deterministic** scripts and configs; easy to re-run the same interview.
- Clear **cost caps** (per-minute pricing, batch vs streaming).
- Minimal dependencies: ingest → transcribe → segment → score → pick → cut → mux.

## Typical stack (illustrative)

- Audio normalize with **ffmpeg** (or equivalent) to a single sample rate / channel layout.
- Single STT provider with **word-level timestamps** when available.
- Simple **segmentation** (silence/pauses or fixed windows + merge).
- **Heuristic salience** first; optional single LLM pass for ranking with a fixed prompt version.
- **SQLite or JSON manifest** for segment store (see [cross-cutting/segment-schema.md](../cross-cutting/segment-schema.md)).

## Out of scope for this tier

- Model training, fine-tuning, or speech-to-speech voice conversion.
- Multi-provider STT ensembling (see [high-risk.md](high-risk.md)).

## Open decisions

- Which single STT provider becomes the default for v1 scripts.
- Whether diarization is required in low-risk or deferred.

## Links

- [high-risk.md](high-risk.md)
- [capability-matrix.md](capability-matrix.md)
- [../execution/complexity-ladder-end-to-end-ideas.md](../execution/complexity-ladder-end-to-end-ideas.md)
- [../pipeline/transcription/README.md](../pipeline/transcription/README.md)
