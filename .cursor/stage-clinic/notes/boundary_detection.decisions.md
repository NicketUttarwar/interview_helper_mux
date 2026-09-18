# Decisions — boundary_detection

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | BD-B1–B4 Wave 2 implement? | yes (unambiguous) | hard transcript+speakers+brief; materialize soft + seed allowlist; prune probe softs; drop OQ invalidates; bind-without-file → LLM |
| 2026-09-17 | L2/L3 | BD-B5 keep skip-when-bound default? | Wave 2 skip — needs_you + FULL_AUTO_REGRESSION_RISK | open |
| 2026-09-17 | L3 | BD-B5 keep skip-LLM-when-bound? | **5A KEEP** (confirm) | `skip_boundary_llm_when_bound=true`; do not force always-LLM |
