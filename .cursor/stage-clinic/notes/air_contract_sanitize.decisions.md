# Decisions — air_contract_sanitize

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | ACS-B1 keep reentry refuse (no nested guard wrap)? | skipped | FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | ACS-B2 contract lifecycle non-LLM? | Wave 2 yes | dependency `lifecycle_phases` execute + drop volley_retry; bootstrap YAML; pytest pin |
| 2026-09-18 | L3 | ACS-B1 reentry refuse confirm? | **1A KEEP** | nested reentry skip → RuntimeError; never heal-done without commit |
