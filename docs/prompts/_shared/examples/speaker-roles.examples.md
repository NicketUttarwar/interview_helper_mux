# speaker-roles examples (reference)

**Good — classic two-person interview**

- `spk_00`: `role: interviewer`, evidence includes “let’s start with your background” and short median turn length.
- `spk_01`: `role: interviewee`, evidence includes long narrative answers to open questions.

**Good — unknown when ambiguous**

- Both speakers similar turn length; `role: unknown` for one or both with **low** `confidence` and `needs` suggesting operator relabel in GUI.

**Bad — longest speaker = interviewee without evidence**

- Assigning interviewee solely because their total word count is higher — violates “do not assign interviewer to the longest speaker without checking question patterns”.

**Bad — all unknown**

- Clear back-and-forth Q&A in first 5 minutes but both `unknown` — violates “do not leave all speakers unknown when the transcript clearly shows Q&A”.
