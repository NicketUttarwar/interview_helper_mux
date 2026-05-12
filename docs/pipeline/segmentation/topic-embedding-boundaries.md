---
id: segmentation-topic-embeddings
tier: high
status: idea
depends_on: [pipeline-segmentation]
---

# Topic and embedding boundaries

High-risk: sliding window of text (or audio embeddings) → **change-point detection** for semantically coherent segments.

## Uses

- Better **story units** for podcast assembly than silence alone.
- Input to **diversity** when picking non-overlapping highlights.

## Open decisions

- Window size vs granularity for short answers.

## Links

- [../scoring-and-selection/diversity-constraints.md](../scoring-and-selection/diversity-constraints.md)
- [../../workflows/parallel-segmentation-candidates.md](../../workflows/parallel-segmentation-candidates.md)
