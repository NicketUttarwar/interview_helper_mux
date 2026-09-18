# Decisions — connector_fuse_pass

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | CFP-B1–B4 implement? | Wave 2 explicit implement | hard:[]; soft islands+manifest; llm_full + ALL_LLM_STAGES; resolve_fuse_round_caps 0→24/8; wrapper skip log after inner SSOT |
| | L2 | CFP-B5 keep incomplete_thought_only + no seam GUI? | needs_you | FULL_AUTO_REGRESSION_RISK if require human seam OK |
| | L2 | CFP-B6 trim vs keep invalidates fan-out? | needs_you | yes if over-clear thrash |
| 2026-09-18 | L3 | CFP-B5/B6 seams + invalidates? | **8A** keep no-human-seam + keep broad invalidates | no operator seam gate; no fan-out trim |
