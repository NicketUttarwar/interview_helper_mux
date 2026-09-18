# Decisions — vo_line_adjudicate

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | B1 Keep HV3 hollow-done refuse? | skipped | FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | B2 fail_open vs loud_fail Full-auto? | skipped | needs_you + FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 CONTINUE | B1 Keep HV3 hollow-done refuse? | KEEP (implicit with fail_open answer scope) | document only; HV3 tests remain; no soft-done |
| 2026-09-17 | L3 CONTINUE | B2 fail_open vs loud_fail? | product default `adjudicate_fail_open=true` — warn + continue on coverage shortfall | `app.defaults.json` + `adjudicate_cfg` fallback True |
