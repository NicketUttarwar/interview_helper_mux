# missing-framing examples (reference)

**Good — envelope-wrapped high-severity gap**

```json
{
  "status": "complete",
  "artifacts": {
    "evaluations": [
      {
        "segment_id": "seg_042",
        "self_explanatory": false,
        "gap_type": "missing_question",
        "secondary_gap_type": null,
        "listener_confusion": "The answer references a 2024 pivot without the prompt that introduced it.",
        "severity": "high"
      }
    ]
  },
  "memory_updates": { "gaps_summary_patch": { "segments_with_gaps": 1, "high_severity": 1 } },
  "needs": [],
  "follow_up_investigations": [],
  "confidence": 0.86,
  "reasoning_summary": "One answer needs its missing prompt restored or replaced."
}
```

**missing_question** — `seg_042` answer discusses a 2024 pivot; no question in source.
- `self_explanatory: false`, `gap_type: missing_question`, `severity: high`

**ok_with_light_bridge** — `seg_018` shifts topic but prior sentence in same segment gives enough context.
- `self_explanatory: true`, `gap_type: ok_with_light_bridge`, `severity: low`

**Do not** mark every answer as missing_question when the interviewer setup exists in an adjacent segment.
