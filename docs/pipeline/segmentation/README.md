---
id: pipeline-segmentation
tier: both
status: spec
depends_on: [pipeline-transcription]
---

# Segmentation

Turn the **continuous transcript + audio** into **candidate segments** for scoring and selection.

## In this folder

| Topic | File |
|-------|------|
| Pause/silence splits | [silence-and-pause-splits.md](silence-and-pause-splits.md) |
| Topic / embedding boundaries | [topic-embedding-boundaries.md](topic-embedding-boundaries.md) |

## Next stage

[../scoring-and-selection/README.md](../scoring-and-selection/README.md)

## Open decisions

- Minimum and maximum segment duration caps.

## Links

- [../../workflows/parallel-segmentation-candidates.md](../../workflows/parallel-segmentation-candidates.md)
