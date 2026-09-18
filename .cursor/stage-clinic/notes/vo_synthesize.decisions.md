# Decisions — vo_synthesize

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | Keep done-without-wav refuse (B1)? | skipped | FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | Contract hard += transitions (B2)? | Wave 2 yes | hard gap_report + master/transitions.json via dependency data + bootstrap; pin test VS-B2 |
| 2026-09-17 | L3 | Full-auto record-line policy (B3)? | skipped | needs_you + FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 CONTINUE | B1 KEEP done-without-wav refuse? | KEEP as-is (honest refuse/incomplete; no soft-done) | document only; no code change (honesty already IN_CODE) |
| 2026-09-17 | L3 CONTINUE | B3 Full-auto record-line policy? | rewrite record-required → synth (unattended owns line) | `rewrite_full_auto_record_lines_to_synth`; G1/stability/resume/stage call sites; ownership ALLOW vo_synthesize on gap delivery |
| 2026-09-18 | optional revisit | Q3B record→synth | only when `voice_reference_approved` | gate in `rewrite_full_auto_record_lines_to_synth`; pin `test_vs_b3_rewrite_requires_voice_ref` |
