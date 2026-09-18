# Decisions — sound_design_vo_finalize

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| | L1\|L2\|L3 | | | |
| 2026-09-17 | L3 | Contract hard += SDP (B2)? | Wave 2 yes | hard vo_synthesize + understanding/sound_design_plan.json via dependency data + bootstrap; pin test SDVF-B2 |
| 2026-09-17 | L3 | Keep refuse-without-heal missing WAV (B1)? | skipped | unambiguous but FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | Trim invalidates vo_line_adjudicate (B3)? | skipped | needs_you |
| 2026-09-18 | L3 | SDVF-B3 trim VO invalidates? | **8B** yes | ADG+contract invalidate edl_narrative_audit+edl only |
