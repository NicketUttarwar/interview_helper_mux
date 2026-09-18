# Decisions — interview_spine_build

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | ISB-B1 stub vs seed omit when disabled? | **4B KEEP stub-in-seed** (confirm) | disabled writes skip stub + heal; remain in seed walk (comment pin in `interview_spine_stage`) |
