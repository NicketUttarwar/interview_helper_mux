# Decisions — content_context

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | Deduplicate soft review_queue (CC-B2)? | Wave 2 yes | drop explicit soft row; keep via transcript_quality_reads |
| | L2/L3 | Hard topology enforce vs soften (CC-B1)? | needs_you | open |
| 2026-09-18 | L3 | Hard topology enforce vs soften (CC-B1)? | Q1A prefer hard→required reads; topology SEED_ORDER hard → harden body | refuse before LLM + preflight; pytest `test_content_context_requires_source_topology` |
