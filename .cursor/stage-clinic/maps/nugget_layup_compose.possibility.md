# Possibility Map — nugget_layup_compose

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | seed **#45** | primary `understanding/nugget_layup_plan.json`
- also authoritative `understanding/gap_report.json` when enabled — `IN_CODE`
- module: `analysis_extended.py::run_nugget_layup_compose`
- OpenAI OF-03b ≤2 (+ optional degraded regen) | Local heavy ML: N/A
- thrash hotspot: QC floors / shards / hosted floor heal pins

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| soft-empty corpus | runs then QC may hard-fail | IN_CODE | `assert_layup_qc_or_raise` |
| unsanitary selection | incompleteness → sanitize | IN_CODE | stage_completion |
| contract hard triad | Soft admit / hard QC exit | CODE_DOC_CONFLICT | |
| disabled | stub plan + force heal | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| selection drift | assert_layup_fresh / epoch unlock | IN_CODE | |
| IP audit | Soft budget input | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| G1 | Optional after gap_report publish — not this stage's wait | IN_CODE | operator-gates |
| G-Framing | Must be Yes for hosted VO path (upstream) | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | plan + gap_report + QC + heal | IN_CODE | |
| sharded &gt;32 | auto_complete=False then force heal after merge | IN_CODE | |
| QC fail | loud fail; no done | IN_CODE | |
| CTA prune | commit_selection_or_refuse | IN_CODE | |
| selection_commit_refused | incompleteness | IN_CODE | |

## 5. Side effects

- plan, gap_report, QC, masks, CTA selection, maybe plan/omit patches — `IN_CODE`
- Invalidates recompose/framing_apply/transitions/vo/edl — ADG `IN_CODE`

## 6. Complexity traps

- Dual SSOT gap_report with compose/recompose — `IN_CODE`
- High coverage floors thrash Full-auto — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard audit+selection+corpus | Soft admit / QC exit | CODE_DOC_CONFLICT |
| primary layup_plan | Matches; gap_report also authoritative | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed/≤2 | refuse / StageError | IN_CODE | |
| degraded regen | +1 attempt path | IN_CODE | |
| hollow | QC assert | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | CTA→LLM→QC→publish gap_report→heal; no GUI modal | IN_CODE | |
| human stall? | No (loud QC / refuse only) | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | High floors; shard mid-fail; hosted floor heal pins | IN_CODE | |
| partial-only fix risk | Lower floors only for partial; G1 must_act here | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- `analysis.nugget_layup.*` floors, batch 32, authoritative_gap_report true

## TEST_GAP

- Mid-shard crash hollow done; Full-auto floor vs soft-pass

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [x] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [x] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Soft vs hard min_nugget_air_coverage at compose vs adjudicate?

## discovery_status

`complete`
