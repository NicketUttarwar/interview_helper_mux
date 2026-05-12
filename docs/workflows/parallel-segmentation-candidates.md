---
id: workflow-parallel-seg
tier: high
status: idea
depends_on: []
---

# Parallel segmentation candidates

Run **two segmenters** (e.g. silence-based vs embedding topics); score each candidate set; pick winner by aggregate metrics or human spot-check.

## Selection ideas

- Higher mean salience after dedupe.
- Fewer **boundary mid-word** errors detected by alignment check.

## Open decisions

- Merge strategies vs pick-one-winner only.

## Links

- [../pipeline/segmentation/topic-embedding-boundaries.md](../pipeline/segmentation/topic-embedding-boundaries.md)
- [../cross-cutting/evaluation-metrics.md](../cross-cutting/evaluation-metrics.md)
