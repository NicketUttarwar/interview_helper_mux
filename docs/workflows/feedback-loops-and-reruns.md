---
id: workflow-feedback-loops
tier: both
status: spec
depends_on: []
---

# Feedback loops and re-runs

You can **improve STT** or **segmentation** and recompute downstream without redoing everything.

## Example loop

```mermaid
flowchart LR
  stt_v1[transcribe_v1]
  seg[segment]
  score[score]
  human[human_review]
  stt_v2[transcribe_v2]
  stt_v1 --> seg --> score --> human
  human --> stt_v2
  stt_v2 --> score
```

## Patterns

- **Re-score only:** same `segment_id` boundaries; refresh text and salience from new transcript.
- **Re-segment:** invalidate boundaries; new `segment_id` namespace or version field ([idempotent-runs.md](idempotent-runs.md)).

## Open decisions

- UI for diffing transcript v1 vs v2 at segment level.

## Links

- [../pipeline/snippet-store/provenance-retranscribe.md](../pipeline/snippet-store/provenance-retranscribe.md)
- [idempotent-runs.md](idempotent-runs.md)
