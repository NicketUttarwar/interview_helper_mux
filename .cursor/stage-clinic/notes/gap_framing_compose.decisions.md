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
| 2026-09-22 | L3 harden | StageInfo companions + stage_key? | yes | declare gap_framing_plan / vo_context_audit; stamp stage_key on writes |
| 2026-09-22 | L3 harden | VO ladder under analysis compose? | skip plan-mutating tiers | pin resume compose; no mastering_plan AuthorityDenied |
| 2026-09-22 | L3 harden | Demote high gaps under framing Yes warrant? | refuse demote-to-green | fill retry then heal_or_raise incompleteness |
| 2026-09-22 | L3 harden | VO budget scale basis? | warrant_gaps not full manifest | `_warrant_gap_count` / episode_structure / selection |
| 2026-09-22 | L3 harden | Shape bind for compose? | advisory until consumers_bind | `compose_plan_bind_mode` GF-02 honesty |
| 2026-09-22 | L3 harden | Layup dual-SSOT flap? | fail-closed no-op | plan↔stamp mismatch refuses LLM |
| 2026-09-22 | L3 harden | missing_framing high without mission? | incompleteness | pin compose preflight |
