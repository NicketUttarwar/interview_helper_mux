---
id: ingest-chunking
tier: both
status: spec
depends_on: [pipeline-ingest]
---

# Chunking long interviews

Cloud STT often caps **payload size** or **duration** per request; hours-long phone files need a **chunk plan** with **overlap** so words on boundaries are not lost.

## Strategies

- Split on **silence** when possible (less mid-word cuts).
- **Fixed windows** (e.g. 10–15 minutes) with **2–5 s overlap**; merge transcripts by timestamp.
- Track `chunk_index` and `t_offset_ms` for global timeline reconstruction.

## Open decisions

- Overlap deduplication: string match vs embedding similarity on boundary windows.

## Links

- [../transcription/word-level-timestamps.md](../transcription/word-level-timestamps.md)
- [../../workflows/feedback-loops-and-reruns.md](../../workflows/feedback-loops-and-reruns.md)
