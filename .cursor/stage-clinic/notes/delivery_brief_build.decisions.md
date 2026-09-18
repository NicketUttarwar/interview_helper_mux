# Decisions — delivery_brief_build

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | Drop circular consumer gap_framing_compose (B1)? | Wave 2 yes | consumers list via contract_dependency_data + bootstrap |
| 2026-09-17 | L3 | Test hard missing gap_report (B2)? | Wave 2 yes | prestage refuse + defect row in test_delivery_brief.py |
