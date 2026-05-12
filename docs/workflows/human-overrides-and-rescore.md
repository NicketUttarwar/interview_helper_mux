---
id: workflow-human-overrides
tier: both
status: spec
depends_on: []
---

# Human overrides and re-score

Human review can **send work back** to scoring or segmentation without starting from raw audio.

## Flow

```mermaid
flowchart LR
  pick[pick_snippets]
  human[human_review]
  score[scoring]
  pick --> human
  human --> score
  human --> pick
```

## Behaviors

- **Boost / ban** signals stored per `segment_id` ([../pipeline/human-review-ui/force-include-exclude.md](../pipeline/human-review-ui/force-include-exclude.md)).
- Optional: re-run **LLM ranker** only on top-K after edits.

## Open decisions

- Whether boosted segments bypass diversity filter.

## Links

- [feedback-loops-and-reruns.md](feedback-loops-and-reruns.md)
