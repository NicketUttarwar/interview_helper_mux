# content-context examples (reference)

**Good — thesis grounded in interviewee**

- `thesis` is one sentence the interviewee could agree with; `topics[].segment_ids` non-empty for major themes.

**Good — claim anchored**

- `key_claims` entry includes `segment_ids` pointing to where the claim was stated.

**Bad — invented claim**

- “Raised Series C in 2024” when transcript only discusses bootstrapping — violates transcript-only rule.

**Bad — generic themes**

- `topics[].name: "Innovation"` with vague summary and no segment_ids — violates “do not copy generic podcast themes without evidence”.

**Bad — ignores transcript_quality**

- High confidence on a topic that falls entirely inside `flagged_chunks` without lowering confidence or noting risk.

**Good — style + identity**

- `memory_updates.interview_identity_patch.one_line_summary` ≤25 words, matches thesis
- `memory_updates.style_patch.tone_class`: `investor` with `tone`: "Measured, numbers-forward — guest leads with metrics, interviewer probes risks"
- `memory_updates.style_patch.format_class`: `one_on_one` for standard Q&A; `panel` when multiple interviewees in speaker roles

**Bad — generic style**

- `tone`: "Insightful conversation" with no evidence from turn patterns or emotional_beats
