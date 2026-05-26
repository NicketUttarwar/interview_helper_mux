# full-master-ranking examples (reference)

**Good — exclude with rationale**

- `excluded_segment_ids`: `[{ "segment_id": "seg_020", "reason": "aside" }]` for a true tangent; thesis still covered by other segments.

**Good — ordering honors constraints**

- `ordered_segment_ids` lists `seg_003` before `seg_010` when narrative plan required it.

**Bad — silent drop**

- Dropping `interviewee_answer` that supports the thesis without an `excluded_segment_ids` entry — violates “do not drop thesis-supporting answer without exclude rationale”.

**Bad — duplicates**

- Same `segment_id` twice in `ordered_segment_ids` — invalid.
