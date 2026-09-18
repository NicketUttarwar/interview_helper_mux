# Decisions — nugget_layup_compose

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | L1: compose-time hard nugget-air floor? | _(awaiting)_ | draft target backlog |
| 2026-09-17 | L3 | NLC-B1 mid-shard crash incompleteness? | Wave 2 yes | `_meta.compose_shards_pending` + stage_completion; heal-if-complete |
| 2026-09-17 | L3 | NLC-B3 contract hard=selection+corpus; audit soft? | Wave 2 yes | `_SKIP_LLM_UPSTREAM_HARD` + soft audit; CONSECUTIVE_SOFT_ALLOWLIST |
| 2026-09-17 | L2/L3 | NLC-B2 compose-time hard nugget-air floor? | Wave 2 skip — needs_you + FULL_AUTO_REGRESSION_RISK | open |
| 2026-09-17 | L3 CONTINUE | NLC-B2 compose-time hard nugget-air floor? | ON | evaluate_layup_qc → evaluate_nugget_air_coverage(hard=True); QC errors block done |
