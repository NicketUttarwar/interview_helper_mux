# Decisions — episode_meta_build

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | Untitled OK? | | B1 needs_you |
| 2026-09-17 | L3 | EMB-B2 hard selection? | Wave 2 yes | refuse before LLM; soft brief+narrative in contract |
| 2026-09-17 | L3 | EMB-B3 stop transcript→meta invalidate? | Wave 2 yes | ADG seed + dependency_data propagation = podcast_publish only |
| 2026-09-17 | L3 | EMB-B1 Untitled policy? | skipped | needs_you + FULL_AUTO_REGRESSION_RISK |
| 2026-09-17 | L3 | EMB-B1 Untitled policy? (6B) | refuse empty/Untitled — require real title before done | `_persist_meta` raises incomplete; pin `test_episode_meta_build_refuses_untitled` |
