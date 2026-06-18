# boundary-detection examples (reference)

**Good — question + answer in one segment (short Q)**

- Single boundary `seg_005`: interviewer asks a 6-word question, then interviewee answers for 90s; one `segment_id`, `proposed_split_reason: question_answer_pair`.

**Good — topic shift**

- Last boundary ends at `end_ms: 120000`; next starts `120800` after a clear pause; `proposed_split_reason: topic_shift`.

**Good — fireside reflective pause (H-SEG-02 calm pace)**

- `pace_class: calm` with a 500 ms reflective pause mid-answer: **do not** split on the 400 ms ladder hit alone; keep one segment unless a 700/1200 ms tier or topic shift applies.

**Good — panel guest handoff**

- Host: "Let's hear from Maria" → guest answers. Split at handoff with `proposed_split_reason: speaker_change`; preserve guest alternation in chronological order.

**Bad — micro-segments**

- Splitting every backchannel “yeah” into its own boundary — violates “do not create hundreds of micro-segments”.

**Bad — overlap**

- Two rows with overlapping `[start_ms, end_ms]` — invalid; should appear in `warnings` and trigger `segment_ambiguity` investigation instead of silent overlap.

**Bad — fireside over-split on 400 ms tier**

- Ten boundaries in two minutes driven only by short reflective pauses when `ladder_guidance` says 400 ms is advisory — prefer longer tiers.

See [04-WAVE-B-audio-structure.md](../../build-out/june182026build/04-WAVE-B-audio-structure.md) for H-SEG-02 promotion gates.
