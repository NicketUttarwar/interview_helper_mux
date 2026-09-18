# Decisions — episode_structure_compose

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | Test analysis_complete withheld when gap pending (B1)? | Wave 2 yes | `test_maybe_finalize_withholds_when_gap_pending` |
| 2026-09-17 | L3 | Drop forward consumers synthesize/confirm/gap_compose (B2)? | Wave 2 yes | consumers via contract_dependency_data + bootstrap |
