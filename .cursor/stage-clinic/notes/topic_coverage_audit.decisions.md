# Decisions — topic_coverage_audit

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | ADG invalidates match contract (B1)? | Wave 2 yes — already matched | pin `propagation` in contract_dependency_data + pytest TCA-B1 |
| 2026-09-17 | L3 | Keep HG-4 voice_ref → missing_framing (B2)? | Wave 2 keep | docstring TCA-B2; existing `test_hg4_voice_ref_heal_pin` |
| 2026-09-17 | L3 | Soft-fail LLM path honesty (B3)? | skipped needs_you + FULL_AUTO_REGRESSION_RISK | leave open |
| 2026-09-17 | L3 | TCA-B3 soft-fail LLM honesty? | **2B KEEP soft-fail** (confirm) | det-first; LLM path via `run_flow_llm_stage` / soft_progression lint; no CSP-05 refuse-all; no harden to incomplete |
| 2026-09-18 | L3 | Q2A CSP-05: soft-fail LLM →? | **incomplete/refuse** (binding) | `auto_complete=False` + `ensure_openai_primary_complete`; hollow coverage incompleteness; pin `test_csp05_*` |
