# Decisions — episode_cover_generate

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | cover_candidates ownership | | B1 |
| 2026-09-17 | L3 | ECG-B1 ALLOW cover_candidates? | Wave 2 yes | `publish/cover_candidates/**` ownership + StageInfo flush dir |
| 2026-09-17 | L3 | ECG-B2 Contract tier reflect OpenAI? | Wave 2 yes | ALL_LLM_STAGES → llm_full; bootstrap YAML |
| 2026-09-17 | L3 | ECG-B3 Assert min size at generate? | Wave 2 yes | `require_cover_min_size(dest, 1400)` after square; mock/host honesty only |
