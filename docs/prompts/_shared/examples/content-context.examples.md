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
