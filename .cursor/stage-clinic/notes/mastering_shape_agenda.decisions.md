# Decisions — mastering_shape_agenda

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | MSA-B1 rubric LLM fail → incomplete vs heuristic? | **2B soft continue** (confirm) | IN_CODE heuristic rubric + `rubric_llm_failed` note + heal; pin `test_msa_b1_rubric_llm_fail_soft_continues` |
| 2026-09-18 | L3 | Q2A CSP-05: rubric LLM fail after ≤2? | **incomplete** (binding) | no heuristic soft-heal; `raise_hollow_openai_primary`; pin `test_msa_b1_rubric_llm_fail_incomplete` |
