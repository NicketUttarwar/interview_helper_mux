# Decisions — edl

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | EDL-B2 Contract SDP producer → sound_design_plan? | Wave 2 yes | soft SDP `producer=sound_design_plan` via dependency data + bootstrap; pin test |
| 2026-09-17 | L3 | EDL-B1 Keep F4 no soft-complete glue? | skipped | FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-18 | L3 | EDL-B1 F4 confirm? | **2A KEEP** | soft=False seam glue; incomplete → pin transitions, never soft-complete EDL |
