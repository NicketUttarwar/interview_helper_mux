# Decisions — gap_framing_compose

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | Small-batch LLM fail assert completeness (B1)? | Wave 2 yes | `_heal_gap_framing_compose_if_complete` after fill+persist; pytest |
| 2026-09-17 | L3 | Align sufficiency min_rows with skip stubs (B3)? | Wave 2 yes | bootstrap `min_count: 0` for gaps |
| 2026-09-17 | L2/L3 | Zero-line after Yes incomplete vs allow (B2)? | Wave 2 skip — needs_you + FULL_AUTO_REGRESSION_RISK | open |
| 2026-09-17 | L3 | GFC-B2 zero-line after Yes? | **2B allow empty persist** | completeness allows `interviewer_lines: []`; skip-stub check only for sanitize/gap_fill_skip producers; pin `test_gfc_b2_zero_line_compose_ok_when_framing_yes` |
| 2026-09-18 | L3 | Q2A CSP-05: framing Yes + zero/hollow lines? | **incomplete** (binding) | `gap_compose_zero_lines_while_framing` + small-batch `auto_complete=False`; pin `test_gfc_b2_zero_line_compose_incomplete_when_framing_yes` |
| 2026-09-18 | optional revisit | Q6B allow empty | framing Yes + zero compose lines OK | helper always None; pin `test_gfc_b2_zero_line_compose_allowed_when_framing_yes` |
