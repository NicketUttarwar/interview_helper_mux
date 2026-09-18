# Decisions — master_transcript_build

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | Dual producer OK? | | B2 |
| 2026-09-17 | L3 | MTB-B1 contract sufficiency min≥1? | Wave 2 yes | bootstrap `_PROCESS_SUFFICIENCY` min_count:1; JSON schema still allows 0 for hollow packs; pytest pin |
| 2026-09-18 | L3 | MTB-B2 dual producer publish inline? | **9A** document dual | stage owns master/*; publish may call MTB heal then copy publish/ |
