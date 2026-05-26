# segment-classification examples (reference)

**Good — Q + A typed correctly**

- `type: interviewer_question`, `speaker_role: interviewer`, `topic_tags: ["go_to_market"]`, `flags: []`.

**Good — answer with callback risk**

- `type: interviewee_answer`, `flags: ["references_prior_missing"]` when they say “like I said in the first half…” without that clip in scope.

**Bad — everything is interviewee_answer**

- Tagging long interviewer monologue as `interviewee_answer` — wrong role and type.

**Bad — invented topic tag**

- `topic_tags: ["crypto_moonshot"]` when the content brief has no such topic and transcript does not support it — contradicts brief.

**Bad — invalid flag string**

- `flags: ["unclear_audio"]` — not in schema; use only `starts_mid_thought`, `references_prior_missing`, `heavy_crosstalk`.
