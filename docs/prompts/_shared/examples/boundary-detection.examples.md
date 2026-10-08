# boundary-detection examples (reference)

**Good — a question is its own segment**

- Interviewer asks a 6-word question, then the guest answers for 90s. Two boundaries: the question, then the answer. `proposed_split_reason: question_answer_pair` marks the seam between them. The question is never folded into the answer.

**Good — long answer split by topic**

- Five-minute interviewee monologue covering product origin, team scaling, and fundraising: **four** segments with `proposed_split_reason: topic_shift` aligned to `content_brief.topics[]`, even when pauses are only 300–500 ms.

**Good — backchannel isolated**

- Guest answers; someone says "yeah" (the word itself, not a diarization flip); guest continues the same concept. Peel the acknowledgment with `proposed_split_reason: backchannel`. The answer before and after stays one concept.

**Good — topic shift**

- Last boundary ends at `end_ms: 120000`; next starts `120800` after a clear pause; `proposed_split_reason: topic_shift`.

**Good — panel guest handoff**

- Host: "Let's hear from Maria" → guest starts a different concept. Split at that concept change with `proposed_split_reason: topic_shift`.

**Bad — single giant segment**

- One 8-minute `interviewee_answer` span covering three content-brief topics — must split at topic boundaries.

**Bad — backchannel swallowed**

- Treating a diarization flip, a period, or a one-second breath as a segment cut while the same concept is still being explained.

**Bad — word-level micro-segments**

- Splitting every 2–3 words or every 400 ms pause inside one sentence — violates min duration and sentence-safe cuts.

**Bad — overlap**

- Two rows with overlapping `[start_ms, end_ms]` — invalid; should appear in `warnings` and trigger `segment_ambiguity` investigation instead of silent overlap.
