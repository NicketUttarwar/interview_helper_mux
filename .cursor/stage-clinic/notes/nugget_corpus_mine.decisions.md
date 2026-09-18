# Decisions — nugget_corpus_mine

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | L1: empty corpus incomplete?; drop QC output claim? | _(awaiting)_ | draft target backlog |
| 2026-09-17 | L3 | NCM-B1 drop QC from contract outputs? | Wave 2 yes | remove `nugget_layup_qc` from mine outputs; ownership stays layup |
| 2026-09-17 | L3 | NCM-B3 demote mastering_plan to soft? | Wave 2 yes | `_SKIP_LLM_UPSTREAM_HARD` + soft plan; selection hard via `_EXTRA_INPUTS`; CONSECUTIVE_SOFT_ALLOWLIST |
| 2026-09-17 | L2/L3 | NCM-B2 empty enabled corpus incomplete? | Wave 2 skip — needs_you + FULL_AUTO_REGRESSION_RISK | keep min_rows:0 / empty done |
| 2026-09-17 | L3 CONTINUE | NCM-B2 empty enabled corpus incomplete? | incomplete (not hollow done) | stage_artifact_incompleteness + auto_complete=False + heal_or_raise; contract min_count:1; disabled empty still OK |
