# content-context examples (reference)

**Good — thesis grounded in interviewee**

- `thesis` is one sentence the interviewee could agree with; topics use non-empty `approx_time_range` (and/or `segment_ids` after reanchor).

**Good — claim anchored (pre-segmentation)**

- `key_claims` entry includes `approx_time_range` like `"05:10-06:05"` where the claim is spoken; `segment_ids` is JSON null until reanchor.

**Good — claim anchored (post-reanchor)**

- `key_claims` entry includes non-empty `segment_ids` pointing to where the claim was stated.

**Bad — empty arrays with no time range**

- `segment_ids: []` and `approx_time_range: null` on a claim — schema-legal empty shape that fails deterministic lint.

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

---

## Scenario: technical_deep_dive

Engineering or product interview with dense jargon, acronyms, and precision claims. Atlas: [interview-scenario-atlas.md](../interview-scenario-atlas.md#technical_deep_dive).

**Good — glossary-aware brief**

- `topics[].name`: "Event-sourced ledger migration" with `segment_ids` covering the explanation block
- `key_claims[]` include `claim_type: definition` with evidence where the guest defines terms
- `memory_updates.style_patch.tone`: "Precise, acronym-heavy — guest assumes listener knows infra basics"
- `jargon_glossary` or entity notes capture at least one term the guest defines in-passing

**Good — honest coverage limits**

- When transcript tail is truncated in volley, `confidence` lowered and `needs` notes shard/decompose — not silent accept
- `emotional_beats` sparse or empty when interview is purely technical — no invented drama

**Bad — layperson thesis on expert content**

- `thesis`: "They shared inspiring lessons about leadership" when transcript is API design and latency numbers
- Topics named "Innovation" / "Technology" with no `segment_ids` tied to specific claims
- `key_claims` state revenue or funding not spoken in transcript

---

## Scenario: human_interest

Personal story, emotional arc, or adversity/recovery narrative — listener connection matters more than jargon. Atlas-adjacent (profile / memoir / human-story formats).

**Good — emotional beats grounded**

- `emotional_beats[]` each cite `segment_ids` where tone shifts (vulnerability, humor, tension, resolution)
- `thesis` centers the guest's stated stakes ("why this mattered to them"), not producer hype
- `memory_updates.interview_identity_patch.one_line_summary` names the guest and situation in ≤25 words
- `topics` follow the story arc (setup → conflict → turning point → outcome), not arbitrary chapter titles

**Good — style matches intimacy**

- `memory_updates.style_patch.format_class`: `one_on_one` with `tone` describing pace (e.g. "Unhurried, long answers — interviewer minimal")
- `audience` reflects who should care emotionally (patients, founders, community) with transcript evidence

**Bad — sensationalized or generic**

- Invented trauma, diagnosis, or relationship details absent from transcript
- `thesis` uses clickbait framing ("You won't believe what happened next")
- Empty `emotional_beats` on an obviously emotional interview — signals model skipped listening
- `topics` list "Inspiration" and "Resilience" without segment anchors

---

## Scenario: investor_one_on_one

Metrics-forward founder/investor conversation — numbers, market, and risk language dominate.

**Good — investor-appropriate brief**

- `memory_updates.style_patch.tone_class`: `investor` with measured tone citing metrics-heavy turns
- `key_claims` separate `opinion` vs `fact` with `segment_ids`; TAM/revenue figures only when spoken
- `topics` ordered by deal narrative (problem → traction → moat → ask) when transcript supports it

**Bad — consumer-marketing voice**

- `thesis` reads like ad copy ("Revolutionary platform changing lives") without guest wording
- Fabricated round size, valuation, or customer counts
