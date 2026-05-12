---
id: snippet-manifest-storage
tier: both
status: spec
depends_on: [pipeline-snippet-store]
---

# Segment manifest and storage

Store **segment records** keyed by stable `segment_id` with time ranges, text, scores, and paths to rendered WAV/FLAC snippets.

## Suggested tables (conceptual)

- `interviews` — one row per source recording.
- `segments` — `t_start_ms`, `t_end_ms`, `text`, `scores`, `status` (candidate, selected, rejected).
- `artifacts` — paths to transcript JSON, rendered clips, mux outputs.

## Open decisions

- Whether snippets are **materialized files** or **virtual** (ffmpeg on demand from master).

## Links

- [../../cross-cutting/segment-schema.md](../../cross-cutting/segment-schema.md)
- [provenance-retranscribe.md](provenance-retranscribe.md)
