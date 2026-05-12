---
id: pipeline-snippet-store
tier: both
status: spec
depends_on: [pipeline-scoring]
---

# Snippet store

The “makeshift database”: **manifests** for segments, scores, audio cut specs, and assembly graphs—SQLite, JSON lines, or both.

## In this folder

| Topic | File |
|-------|------|
| Tables / files layout | [segment-manifest-and-storage.md](segment-manifest-and-storage.md) |
| Re-transcribe and immutability | [provenance-retranscribe.md](provenance-retranscribe.md) |

## Next stage

[../audio-editing/README.md](../audio-editing/README.md)

## Open decisions

- Single SQLite file per interview vs global catalog.

## Links

- [../../cross-cutting/segment-schema.md](../../cross-cutting/segment-schema.md)
