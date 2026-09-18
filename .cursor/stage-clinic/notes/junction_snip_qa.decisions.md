# Decisions — junction_snip_qa

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | Rename advisory mode? | | B1 |
| 2026-09-17 | L1 | Full-auto osc policy? | | B3 needs_you |
| 2026-09-17 | L3 | JSQ-B1 document advisory dual meaning? | Wave 2 yes | keep default `advisory`; doc EM8 incomplete always blocks; config-keys + defaults comment + pytest |
| 2026-09-17 | L3 | JSQ-B2 thrash golden mix⇄junction? | Wave 2 yes | i25 handshake pin + refuse_mix/junction-first |
| 2026-09-17 | L3 | JSQ-B3 Full-auto osc/budget remediation? | skip | needs_you + FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | JSQ-B4 selection hard vs `_check`? | Wave 2 yes | soft+correctness via dependency_data; drop `_CORRECTNESS_TO_HARD`; bootstrap YAML |
| 2026-09-17 | L3 CONTINUE | JSQ-B3 Full-auto osc/budget: remediation vs needs_operator? | KEEP needs_operator | notes/target/ledger only — NO code change to switch to classified remediation; budget/osc exhaust stays needs_operator (IN_CODE) |
| 2026-09-17 | L3 CONTINUE (rebind) | JSQ-B3 osc/budget exhaust policy? | CLASSIFIED REMEDIATION / refuse terminate — NO needs_operator hang | `junction_budget_exhaust_hard_pin` no longer stamps `needs_operator`; classified markers in `operator_gates`; terminal `raise_loud_failure` refuses critical residuals; pytest pins |
