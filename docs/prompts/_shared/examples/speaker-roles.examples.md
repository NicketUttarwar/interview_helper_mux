# speaker-roles examples (reference)

**Good — classic two-person interview**

- `spk_00`: `role: interviewer`, `narrative_function: frame`, evidence includes “let’s start with your background”.
- `spk_01`: `role: interviewee`, `narrative_function: storyteller`, long narrative answers.
- `conversation_profile.format_class_candidate: one_on_one`, `format_confidence: 0.9`.
- `gap_sensitivity.severity_hints.missing_setup: strict`.

**Good — panel with moderator**

- `spk_00`: `role: moderator`, `narrative_function: frame`.
- `spk_01`, `spk_02`: `role: panelist`, distinct substantive answers.
- `format_class_candidate: panel`, `segment_focus: interviewee_answer_per_guest` in gap_sensitivity.
- `priority_gap_types` includes `missing_definition`.

**Good — ambiguous layout with hypotheses (E)**

- `format_confidence: 0.55` — emit two hypotheses:
  - `hyp_one_on_one`: co-host interpreted as interviewer + single interviewee
  - `hyp_panel`: moderator + two panelists
- Leave `confirmed_conversation_hypothesis_id: null`; operator picks at handoff.

**Good — co-host frame**

- `spk_00`: `interviewer` (opens/closes, owns pivots).
- `spk_01`: `co_host` (follow-ups, audience proxy) — evidence cites question density not length.
- `spk_02`: `interviewee`, `narrative_function: storyteller`.

**Good — off-mic**

- `spk_03`: `off_mic`, evidence: “producer cue / laughter burst, non-substantive”.

**Bad — longest speaker = interviewee without evidence**

- Assigning interviewee solely because word count is higher — violates question-pattern rule.

**Bad — all unknown with clear Q&A**

- First five minutes show explicit questions and answers but every speaker `unknown` — lint fail.

**Bad — collapsing panel guests**

- Two distinct guests both labeled `interviewee` without `panelist` when `format_class_candidate: panel`.
