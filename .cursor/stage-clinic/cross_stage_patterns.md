# Cross-stage patterns

When the same footgun appears in ≥3 stages, add a row and prefer one shared host rule.

| id | pattern | stages (≥3) | shared rule proposal | status | DoD check |
|----|---------|-------------|----------------------|--------|-----------|
| CSP-01 | Disabled / skip path returns without artifact + heal → seed pending | low_conf_island_scan, air_script enable=false (map), interview_spine enabled=false (map) | Always write skip/disabled artifact then `heal_or_refuse_mark` | ruled (low_conf Wave 2); others deferred | 1, 2 |
| CSP-02 | Contract soft inputs that body treats hard (or reverse) | mix, sonic_context_build, content_context, speaker_roles, many delivery | Align contract via `contract_dependency_data` OR harden body to match declared | open | 2, 7 |
| CSP-03 | Unattended `needs_operator` stamped for classified blocks | all delivery under wrong gate helper | Classified allowlist for **0.2.0** unattended (not 0.1-only) | ruled (Wave 2 `should_stamp_needs_operator`) | 3, 5 |
| CSP-04 | mix ⇄ junction incomplete_cut / remaster thrash | mix, junction_snip_qa, transitions | One remaster authority + no-delta / attempt memo already partial; finish honesty edges | open | 1, 6 |
| CSP-05 | Hollow OpenAI / soft-fail still heals done | mastering_research_routing, gap_framing_compose, episode_meta, others | Refuse or incomplete when primary hollow after ≤2 attempts | open | 2, 4 |
| CSP-06 | Skip vs primary dual SSOT (prepare) | audio_preclean (skip.json vs isolated.wav) | incompleteness accepts either finished outcome | ruled (Wave 2 stage_completion) | 2, 5 |
