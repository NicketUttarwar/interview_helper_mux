# topic-coverage-audit examples (reference)

**Good — envelope-wrapped topic and claim mapping**

```json
{
  "status": "complete",
  "artifacts": {
    "topic_mappings": [
      { "topic": "Series A fundraise", "segment_ids": ["seg_012", "seg_018"], "covered": true }
    ],
    "claim_mappings": [
      { "claim": "The team changed ICP after enterprise pilots.", "segment_ids": ["seg_018"], "covered": true }
    ],
    "missing_coverage": [],
    "orphan_segment_ids": [],
    "coverage_score": 1.0
  },
  "memory_updates": { "confidence_patch": { "coverage": 1.0 } },
  "needs": [],
  "follow_up_investigations": [],
  "confidence": 0.88,
  "reasoning_summary": "Every brief topic and claim has segment support."
}
```

**Good — topic mapped**

- `topic_mappings` entry: `topic: "Series A fundraise"`, `segment_ids: ["seg_012", "seg_018"]`, `covered: true`.

**Good — honest miss**

- Brief lists claim “EU regulatory timeline” but transcript never mentions EU — `missing_coverage` with `item` + `suggestion: "may need follow-up interview or drop claim from brief"` and `follow_up_investigations` with `theme_unmapped` or operator `needs` if blocking.

**Bad — fake coverage**

- `covered: true` with empty `segment_ids` — invalid against intent of audit.

**Bad — ignoring claims**

- `claim_mappings` omitted while `content_brief.key_claims` is non-empty — claims must be mapped or explicitly missing.
