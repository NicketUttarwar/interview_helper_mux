# Decisions — full_master_ranking

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | L1: QC fail Full-auto policy?; contract hard align | _(awaiting)_ | draft target backlog |
| 2026-09-17 | L3 | FMR-B1 align contract hard with checker? | Wave 2 yes | hard = narrative+manifest+gap; fuse+coverage soft; bootstrap `_SKIP_LLM_UPSTREAM_HARD`; CONSECUTIVE_SOFT_ALLOWLIST |
| 2026-09-17 | L2/L3 | FMR-B2 Full-auto QC-fail policy (strict vs soft)? | Wave 2 skip — needs_you + FULL_AUTO_REGRESSION_RISK | open |
| 2026-09-17 | L3 | FMR-B2 Full-auto QC-fail policy? | operator CONTINUE: soft/advisory continue unless already soft | `check_narrative_qc` Full-auto softens SystemExit; manual keeps strict; already-soft unchanged |
