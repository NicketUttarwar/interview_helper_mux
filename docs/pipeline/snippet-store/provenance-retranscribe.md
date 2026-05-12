---
id: snippet-provenance
tier: both
status: spec
depends_on: [pipeline-snippet-store]
---

# Provenance and re-transcribe

When STT or segmentation config changes, old **segment_ids** may no longer point at the same words.

## Strategies

- **Immutable snapshots:** keep transcript v1 alongside v2; segments reference `transcript_revision`.
- **Re-score only:** same boundaries, new text from better STT ([../../workflows/feedback-loops-and-reruns.md](../../workflows/feedback-loops-and-reruns.md)).

## Open decisions

- Automatic invalidation rules when word timestamps shift beyond N ms.

## Links

- [../../workflows/idempotent-runs.md](../../workflows/idempotent-runs.md)
