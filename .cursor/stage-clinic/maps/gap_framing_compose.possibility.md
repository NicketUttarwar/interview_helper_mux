# Possibility Map — gap_framing_compose

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | OA-08
- primary: `understanding/gap_report.json` (+ interviewer_script.txt, gap_framing_plan, vo context audit)
- module: `pipeline._run_gap_framing_compose_stage` → `gaps.run_gap_framing_compose`
- hard: gap_evaluations + mastering_plan
- gate: G1 optional later (not this stage); G-Framing already decided
- thrash: yes (layup authority no-op, high_gap fill, shard merge)
- tests: solid (gap framing gates, hg2, high gap, layup)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gap_fill skipped | ensure skip stub; return | IN_CODE | `_run_gap_framing_compose_stage` |
| layup authority / seat freeze | No-op; heal if not done | IN_CODE | early return |
| all hard + framing on | LLM compose (full or shards); persist companions | IN_CODE | |
| LLM total fail | high_gap_vo fill seed | IN_CODE | |
| empty interviewer_lines | Fill high gaps; may still heal/incomplete | IN_CODE | |
| hollow report | Completeness assert / heal_or_raise | IN_CODE | |
| research thin | Admit refuse unless skipped | IN_CODE | A-01 |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| missing_framing + plan | Proceed | IN_CODE | |
| layup plan exists later | Re-entry no-ops | IN_CODE | |
| soft delivery_brief/episode absent | OK (soft) | IN_CODE | analysis order |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| G1 | Not armed here; optional after | IN_CODE | operator-gates |
| framing pending | Should already be clear | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | gap_report + script + companions; heal | IN_CODE | |
| shard fail | Continue siblings + fill | IN_CODE | |
| incomplete after persist | Log warning; may not mark done | IN_CODE | StageArtifactsIncompleteError |
| soft fail | Fill path still persists | IN_CODE | honesty risk if hollow done |

## 5. Side effects

- Writes: gap_report, interviewer_script, gap_framing_plan, gap_vo_context_audit, speaker_delivery_plan companions — `IN_CODE` `persist_gap_framing_companion_artifacts`
- Seeds refinement hook `after_gap_compose_hook` — `IN_CODE`
- Consumers: delivery_brief, delivery ranking/VO chain — contract

## 6. Complexity traps

- OpenAI + high_gap fill + demote + repair — `IN_CODE`
- Layup dual SSOT for gap_report — `IN_CODE`
- Local heavy ML: N/A (VO synth later)

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard evals + plan | Matches | IN_CODE |
| sufficiency gaps≥1 | May conflict with legit empty after skip/fill | CODE_DOC_CONFLICT |
| soft delivery_brief | Soft; delivery_brief is downstream in seed | CODE_DOC_CONFLICT timing |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed / ≤2 | Fail → fill | IN_CODE | llm_simple / run_analysis_llm_stage |
| hollow persist | Incomplete helpers / HG-2 family | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + framing Yes | Runs unattended; G1 optional later | IN_CODE | |
| Full-auto + framing No | Skip path | IN_CODE | |
| human stall? | No at this stage | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Soft-success after empty shards without lines | IN_CODE | DoD honesty |
| partial-only fix risk | Forcing G1 must_act here | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- gap_fill.* (skip path)
- creative_delivery.required (assert floors elsewhere)
- batch size via coverage_limits gap_pass

## TEST_GAP

- Soft-success empty lines after all shards fail
- sufficiency min_rows vs skip stub

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [x] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Empty legit gap_report after Yes — refuse incomplete or allow zero-line ship?

## discovery_status

`complete`
