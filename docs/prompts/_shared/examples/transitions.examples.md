# transitions examples (reference)

**Good — short bridge**

- `{ "after_segment_id": "seg_005", "before_segment_id": "seg_012", "text": "So when the product finally shipped, what broke first?", "type": "topic_shift" }` — tees up without summarizing the answer.

**Good — empty when adjacent works**

- `transitions: []` when two segments need no bridge.

**Bad — duplicates gap VO**

- Long line that repeats text already in `gap_report` for `before_segment_id` — violates “do not duplicate gap_report VO lines”.

**Bad — summarizes upcoming answer**

- “Next they explain how they fired half the team and rebuilt culture” before the clip — violates “do not repeat the upcoming answer”.

**Bad — meta cliché**

- “In this next segment we’ll hear about…” — avoid unless truly necessary.
