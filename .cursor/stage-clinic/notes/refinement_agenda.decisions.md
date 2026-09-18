# Decisions — refinement_agenda

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | L1: block agenda when gap unsanitary? | _(awaiting)_ | draft target backlog |
| 2026-09-17 | L3 | RA-B1 demote gap_report hard→soft? | Wave 2 yes | hard:[]; soft gap+coverage/plan/evals/topology; EMPTY_HARD + consecutive soft allowlist; bootstrap YAML |
| 2026-09-17 | L3 | RA-B3 confirm ranking hole injection test? | Wave 2 yes | pytest covers confirm appends ranking + force heal |
| 2026-09-17 | L3 | RA-B2 block agenda when gap unsanitary? | skipped needs_you + FULL_AUTO_REGRESSION_RISK | leave open |
| 2026-09-17 | L3 | RA-B2 block agenda when gap unsanitary? | operator CONTINUE: yes block | present dirty gap raises gap_unsanitary (missing stays soft RA-B1); pytest |
