# Decisions — content_brief_reanchor

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | CBR-B1 speakers hard? | Wave 2 yes | contract hard matches `build_input` hard-read |
| 2026-09-17 | L3 | CBR-B2 drop optimal_questions invalidates? | Wave 2 yes | dependency data + ADG seed |
| 2026-09-17 | L3 | CBR-B3 keep completeness RuntimeError + test? | Wave 2 yes | gate kept; test forces partial status (repairs heal thin payloads) |
| 2026-09-17 | L2/L3 | CBR-B4 resplit↔reanchor oscillation caps? | Wave 2 skip — needs_you | open |
| 2026-09-18 | L3 | CBR-B4 resplit↔reanchor thrash? | **5A** thrash_hardening only | no stage-local caps |
