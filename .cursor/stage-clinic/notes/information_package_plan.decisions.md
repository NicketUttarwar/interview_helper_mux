# Decisions — information_package_plan

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L1 | L1: empty corpus incomplete vs warn? | _(awaiting)_ | draft target backlog |
| 2026-09-17 | L3 | IPP-B1 drop llm_execute? | Wave 2 yes | lifecycle `execute` via dependency_data + bootstrap; StageInfo openai=() |
| 2026-09-17 | L3 | IPP-B2 empty corpus incomplete vs warn? | skip | needs_you + FULL_AUTO_REGRESSION_RISK=yes |
| 2026-09-17 | L3 | IPP-B3 document commit_music_vo Full-auto default? | Wave 2 yes | information-packages.md + config-keys + defaults_inventory; comment in dependency_data |
| 2026-09-17 | L3 CONTINUE | IPP-B2 empty corpus incomplete vs warn? | incomplete (not warn-and-done) | require_corpus+empty writes audit evidence then heal_or_raise refuses; incompleteness pin resume nugget_corpus_mine |
