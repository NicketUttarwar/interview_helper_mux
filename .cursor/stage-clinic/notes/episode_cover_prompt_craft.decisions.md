# Decisions — episode_cover_prompt_craft

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | Keep F7 fail-open | assumed yes | B1 only |
| 2026-09-17 | L3 | ECPC-B1 empty prompt incomplete? | Wave 2 yes | `_episode_cover_prompt_craft_incompleteness`; pytest |
| 2026-09-17 | L3 | ECPC-B2 contract soft meta? | Wave 2 yes | hard:[]; soft meta+brief+selection; SKIP_LLM_UPSTREAM; allowlists; bootstrap YAML |
