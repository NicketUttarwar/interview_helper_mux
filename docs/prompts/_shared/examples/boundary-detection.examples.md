# boundary-detection examples (reference)

**Good — question + answer in one segment (short Q)**

- Single boundary `seg_005`: interviewer asks a 6-word question, then interviewee answers for 90s; one `segment_id`, `proposed_split_reason: question_answer_pair`.

**Good — topic shift**

- Last boundary ends at `end_ms: 120000`; next starts `120800` after a clear pause; `proposed_split_reason: topic_shift`.

**Bad — micro-segments**

- Splitting every backchannel “yeah” into its own boundary — violates “do not create hundreds of micro-segments”.

**Bad — overlap**

- Two rows with overlapping `[start_ms, end_ms]` — invalid; should appear in `warnings` and trigger `segment_ambiguity` investigation instead of silent overlap.
