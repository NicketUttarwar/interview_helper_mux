# topic-coverage-audit examples (reference)

**Good — topic mapped**

- `topic_mappings` entry: `topic: "Series A fundraise"`, `segment_ids: ["seg_012", "seg_018"]`, `covered: true`.

**Good — honest miss**

- Brief lists claim “EU regulatory timeline” but transcript never mentions EU — `missing_coverage` with `item` + `suggestion: "may need follow-up interview or drop claim from brief"` and `follow_up_investigations` with `theme_unmapped` or operator `needs` if blocking.

**Bad — fake coverage**

- `covered: true` with empty `segment_ids` — invalid against intent of audit.

**Bad — ignoring claims**

- `claim_mappings` omitted while `content_brief.key_claims` is non-empty — claims must be mapped or explicitly missing.
