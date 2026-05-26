# narrative-arc-plan examples (reference)

**Good — constraint encodes dependency**

- `ordering_constraints`: `{ "before_segment_id": "seg_003", "after_segment_id": "seg_010", "reason": "origin story before scale-up numbers" }` when seg_003 is setup and seg_010 is payoff.

**Good — chapter opens on real segment**

- `chapters[0].suggested_open_segment_id` equals a manifest `segment_id` that opens the thesis.

**Bad — ghost segment id**

- `suggested_open_segment_id: "seg_999"` not in manifest — breaks schema intent and downstream ranking.

**Bad — chronological-only**

- `arc_summary` says “order follows recording order” with no editorial arc — violates “do not plan chronological-only arc without editorial reason” when the interview is reorderable.
