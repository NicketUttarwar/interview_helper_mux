# Coherence (H-ORC-03) volley examples

## topic_coverage_audit input slice

```json
{
  "coherence_summary": {
    "activated": true,
    "summary": { "topic_drift_count": 1, "missing_callback_count": 1 },
    "risks": [
      {
        "kind": "topic_drift",
        "time_ms": 1320000,
        "confidence": 0.62,
        "theme_id": "platform_strategy"
      }
    ]
  }
}
```

Action: add `topic_mappings` or document exclude — do not ignore drift at 22:00.

## content_brief_reanchor

Use `claim_contradiction` risk to split or qualify conflicting `key_claims` with distinct `segment_ids`.
