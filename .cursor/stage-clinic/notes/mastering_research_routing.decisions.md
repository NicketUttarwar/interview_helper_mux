# Decisions — mastering_research_routing

brain: 0.2.0

| ts | layer | question | answer | implication |
|----|-------|----------|--------|-------------|
| 2026-09-17 | L1 | L1: when research.llm.enabled, fail → refuse or degraded stub? | _(awaiting)_ | MRR-B1 needs_you |
| 2026-09-17 | L3 | MRR-B2 log+stamp llm_failed; no empty except? | Wave 2 implement | stub keeps heal; action_id + llm_failed/authoritative=false/fail_reason |
| 2026-09-17 | L3 | MRR-B1 LLM fail: refuse vs stub? | **2B KEEP stub** (confirm) | IN_CODE `_sequential_stub_routing(llm_failed=True)` + heal; do **not** hard refuse; no CSP-05 refuse-all |
| 2026-09-18 | L3 | Q2A CSP-05: LLM fail/hollow after ≤2? | **refuse/incomplete** (binding) | write diagnostic llm_failed stub; `raise_hollow_openai_primary`; no heal-done; pins in `test_a03_*` + `openai_primary_honesty` |
| 2026-09-18 | L3 | CSP-02 hard SDP empty-hard lie? | Q1A match hard→required reads | hard:[]; no empty-hard promote from palettes |
