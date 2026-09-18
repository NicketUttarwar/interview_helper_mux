# Decisions — sfx_prompt_craft

Append-only.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | Full-auto G1.5 when QA warnings? | | B2 needs_you |
| 2026-09-17 | L3 | SPC-B1 consumers → mmaudio_sfx? | Wave 2 yes | dependency data + bootstrap YAML |
| 2026-09-17 | L3 | SPC-B2 Full-auto G1.5 beyond first_try green? | skipped | needs_you + FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | SPC-B3 refuse default/empty SDP assets? | Wave 2 yes | body RuntimeError before LLM; pytest |
| 2026-09-17 | L3 | SPC-B2 Full-auto G1.5 incl. soft warnings? | AUTO-APPROVE on Full-auto including soft warnings (not only first_try green) | `maybe_auto_approve_prompt_review`: Full-auto → `auto_full_auto`; Partial/manual still first_try-green-only; defaults_inventory |
