# Decisions — segment_classification

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | SC-B1 hard transcript+speakers? | Wave 2 yes | contract hard matches SEGMENTATION_INPUT_DEPS (+ boundaries via LLM_UPSTREAM) |
| 2026-09-17 | L3 | SC-B2 prune soft edl + probe/review? | Wave 2 partial | drop `master/edl.json`; keep `transcript_quality_reads()` — body calls `transcript_quality_for_ctx` (ICP-B1 precedent) |
| 2026-09-17 | L3 | SC-B3 drop optimal_questions invalidates? | Wave 2 yes | dependency data + ADG seed |
| 2026-09-17 | L3 | SC-B4 det early-return post-hooks? | Wave 2 yes | shared `_classification_post_hooks`: topic_bootstrap + seed refresh; specialists when payload builds |
| 2026-09-17 | L2/L3 | SC-B5 keep skip-when-bound default? | Wave 2 skip — needs_you + FULL_AUTO_REGRESSION_RISK | open |
| 2026-09-17 | L2/L3 | SC-B6 resplit↔classification thrash caps? | Wave 2 skip — needs_you | open |
| 2026-09-17 | L3 | SC-B5 keep skip-LLM-when-bound? | **5A KEEP** (confirm) | `skip_classification_llm_when_bound=true`; do not force always-LLM |
| 2026-09-18 | L3 | SC-B6 resplit↔classification thrash? | **5A** thrash_hardening only | no stage-local re-entry caps |
