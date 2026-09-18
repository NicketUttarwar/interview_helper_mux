# Decisions — transitions

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | B2 align hard inputs with payload? | Wave 2 yes | content_brief+gap_report hard + preflight; selection stays; bootstrap YAML |
| 2026-09-17 | L3 | B3 ADG invalidates match contract? | Wave 2 yes — already matched | pin `propagation` in contract_dependency_data + pytest transitions-B3 |
| 2026-09-17 | L3 | B1 empty transitions Full-auto honesty? | skipped | needs_you + FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 CONTINUE | B1 empty transitions OK under Full-auto? | YES keep empty OK (min_rows 0) | document; verified contract sufficiency min_count=0 + llm_simple empty persist path; no code patch (no refuse-empty drift) |
