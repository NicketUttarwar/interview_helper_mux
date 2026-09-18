# Decisions — ideal_cuts_propose

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | ICP-B1 prune soft review_queue/golden_facts/protected_zones? | Wave 2 skip — code reads via `transcript_quality_for_ctx` | keep `transcript_quality_reads()`; discovery "unused" was false |
| 2026-09-17 | L3 | ICP-B2 surface `min_span_coverage_ratio` in defaults? | Wave 2 yes | `app.defaults.json` ideal_cuts → `0.45` |
| 2026-09-17 | L3 | ICP-B4 span persist → StageError after attempt 2? | Wave 2 yes | `llm_simple` wraps retryable span RuntimeError as StageError; no fail-open |
| | L2/L3 | enable=false stub force-done (ICP-B3)? | needs_you + FULL_AUTO_REGRESSION_RISK | open |
| 2026-09-17 | L3 | ICP-B3 enable=false stub? | **4B KEEP stub** (confirm) | placeholder cut + `heal_or_refuse_mark` force; keep progressing |
