# Cross-stage patterns

When the same footgun appears in ≥3 stages, add a row and prefer one shared host rule.

| id | pattern | stages (≥3) | shared rule proposal | status | DoD check |
|----|---------|-------------|----------------------|--------|-----------|
| CSP-01 | Disabled / skip path returns without artifact + heal → seed pending | low_conf_island_scan, air_script enable=false, interview_spine enabled=false | Always write skip/disabled artifact then `heal_or_refuse_mark` | ruled (low_conf + air_script ASC-B2/ASS-B2 Wave 2; spine ISB-B2) | 1, 2 |
| CSP-02 | Contract soft inputs that body treats hard (or reverse) | mix, sonic_context_build, content_context, speaker_roles, many delivery | Align contract via `contract_dependency_data` OR harden body to match declared | **ruled** (Q1A 2026-09-18: CC-B1 harden topology; MRW/MRR/MRRoll demote false empty-hard; MPC-B2 producer=plan + body require SDP; mix/SCB prior) — leftovers if any stay map-tagged outside this sweep | 2, 7 |
| CSP-03 | Unattended `needs_operator` stamped for classified blocks | all delivery under wrong gate helper | Classified allowlist for **0.2.0** unattended (not 0.1-only) | ruled (Wave 2 `should_stamp_needs_operator`) | 3, 5 |
| CSP-04 | mix ⇄ junction incomplete_cut / remaster thrash | mix, junction_snip_qa, transitions | One remaster authority + no-delta / attempt memo; osc/budget → classified refuse terminate (no needs_operator) | ruled (pins + g_listen auto-clear + JSQ-B3 classified refuse) | 1, 3, 6 |
| CSP-05 | Hollow OpenAI / soft-fail still heals done | mastering_research_routing, mastering_shape_agenda, mastering_shape_candidates, topic_coverage_audit, gap_framing_compose (+ episode_meta prior) | Shared `openai_primary_honesty.raise_hollow_openai_primary` / incompleteness after ≤2 attempts — no soft-success heal-done | **ruled** (Q2A + MSC-B2 2B: candidates when shape.llm on) | 2, 4 |
| CSP-06 | Skip vs primary dual SSOT (prepare) | audio_preclean (skip.json vs isolated.wav) | incompleteness accepts either finished outcome | ruled (Wave 2 stage_completion) | 2, 5 |
