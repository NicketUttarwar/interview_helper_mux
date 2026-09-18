# Decisions — air_script_compose

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | L1: disabled skip-done?; omit shrink selection? | _(awaiting)_ | draft target backlog |
| 2026-09-17 | L3 | ASC-B1 retier process? | Wave 2 yes | `_PROCESS_STAGES` + dependency lifecycle execute; bootstrap YAML; pytest pin |
| 2026-09-17 | L3 | ASC-B2 disabled heal/skip-done? | skipped | FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | ASC-B3 Pass A omit shrink selection? | skipped | needs_you |
| 2026-09-17 | L3 | ASC-B2 CONTINUE: enable=false skip-done (CSP-01) | Wave 2 yes (operator override FARR skip) | `persist_air_script_disabled_skip` + heal; omit_ledger empty latch; ASC-B3 still needs_you |
| 2026-09-17 | L3 | ASC-B3 Pass A omit shrink selection? (1B) | leave selection alone — do NOT shrink | `compose_pass_a` records omits on plan/ledger only; no `commit_selection_or_refuse`; pin `test_asc_b3_pass_a_omits_leave_selection_unchanged` |
