# Decisions — mastering_shape_candidates

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | MSC-B1 test forced sparse survivor? | Wave 2 yes | empty `mode_candidates` → `cand_forced_sparse`; pytest pin |
| 2026-09-17 | L2/L3 | MSC-B2 require LLM candidates if shape.llm on + no fallback? | Wave 2 skip — needs_you + FULL_AUTO_REGRESSION_RISK | keep fail-open heuristic |
| 2026-09-18 | L3 | MSC-B2 LLM-only when shape.llm on? | **2B** no heuristic/forced-sparse heal | CSP-05 raise_hollow; defaults llm=false unchanged |
