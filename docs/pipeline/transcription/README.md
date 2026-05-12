---
id: pipeline-transcription
tier: both
status: spec
depends_on: [pipeline-ingest]
---

# Transcription

Speech-to-text: provider choice, **timestamps**, optional **diarization**, and adapter pattern for swapping implementations.

## In this folder

| Topic | File |
|-------|------|
| Word-level alignment | [word-level-timestamps.md](word-level-timestamps.md) |
| Provider abstraction | [stt-provider-adapters.md](stt-provider-adapters.md) |
| Who spoke when | [diarization.md](diarization.md) |

## Next stage

[../segmentation/README.md](../segmentation/README.md)

## Open decisions

- Default language auto-detect vs fixed locale.

## Links

- [../../versions/capability-matrix.md](../../versions/capability-matrix.md)
