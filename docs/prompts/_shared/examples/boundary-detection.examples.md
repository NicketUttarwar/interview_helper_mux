# boundary-detection examples (reference)

**Good — question + answer in one segment (short Q, no backchannel between)**

- Single boundary `seg_005`: interviewer asks a 6-word question, then interviewee answers for 90s with no intervening host turn; one `segment_id`, `proposed_split_reason: question_answer_pair`.

**Good — long answer split by topic**

- Five-minute interviewee monologue covering product origin, team scaling, and fundraising: **four** segments with `proposed_split_reason: topic_shift` aligned to `content_brief.topics[]`, even when pauses are only 300–500 ms.

**Good — backchannel isolated**

- Guest answers; host says "yeah" (2 words, diarization flip); guest continues. Three segments: answer block A → `interviewer_reaction` → answer block B (`speaker_change` on the backchannel).

**Good — topic shift**

- Last boundary ends at `end_ms: 120000`; next starts `120800` after a clear pause; `proposed_split_reason: topic_shift`.

**Good — panel guest handoff**

- Host: "Let's hear from Maria" → guest answers. Split at handoff with `proposed_split_reason: speaker_change`; preserve guest alternation in chronological order.

**Bad — single giant segment**

- One 8-minute `interviewee_answer` span covering three content-brief topics — must split at topic boundaries.

**Bad — backchannel swallowed**

- Host "right", "interesting", "sure" kept inside one 4-minute answer — split each brief turn when diarization shows speaker change.

**Bad — word-level micro-segments**

- Splitting every 2–3 words or every 400 ms pause inside one sentence — violates min duration and sentence-safe cuts.

**Bad — overlap**

- Two rows with overlapping `[start_ms, end_ms]` — invalid; should appear in `warnings` and trigger `segment_ambiguity` investigation instead of silent overlap.

See [04-WAVE-B-audio-structure.md](../../build-out/june182026build/04-WAVE-B-audio-structure.md) for H-SEG-02 promotion gates.
