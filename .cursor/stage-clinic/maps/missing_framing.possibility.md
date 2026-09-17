# Possibility Map — missing_framing

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | OA-07
- primary: `understanding/gap_evaluations.json`
- module: `pipeline._run_missing_framing_stage` → `gaps.run_missing_framing`
- hard: boundaries, content_brief, manifest, mastering_plan
- gate: **G-Framing** (+ G-Speaker / G-VoiceRef / G-Delivery when Yes)
- thrash: yes (batch_fill, coverage CAP, voice-ref pins)
- tests: solid (hg3, gates, gap_fill, hv*, hu2)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| G-Framing pending | Auto-accept via homunculus/auto_accept OR wait | IN_CODE | `maybe_auto_accept_gap_gate_defaults` / `require_gap_framing_decision_clear` |
| G-Framing No | Skip stub path; return | IN_CODE | `ensure_gap_fill_skipped` |
| G-Framing Yes + ineligible | Loud fail unless auto_skip | IN_CODE | `_run_missing_framing_stage` |
| all hard present + Yes | Sharded OpenAI evals; heal | IN_CODE | `run_missing_framing` |
| batch_fill leftovers | Persist fills; **refuse done** | IN_CODE | `_missing_framing_batch_fill_incompleteness` |
| coverage CAP exhausted | Seal leftovers; heal | IN_CODE | `MISSING_FRAMING_COVERAGE_CAP=2` |
| hollow evaluations | Schema + incompleteness | IN_CODE | |
| research shape-core thin | Admit refuse (unless gap skipped) | IN_CODE | A-01 |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| plan provisional | Allowed (Pass1) | IN_CODE | seed order |
| plan invalidated | Re-run | IN_CODE | |
| leftover reentry | Coverage pass shards | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gate open / waiting | Overlay may-pause; Full-auto/Partial driver auto-Yes | IN_CODE | `partialAcceleratedGuard.ts` / homunculus |
| gate answered Yes | Continue path clears | IN_CODE | `set_gap_framing_enabled` |
| gate answered No | Skip | IN_CODE | |
| illegal skip | Blocked by require_* | IN_CODE | `require_gap_path_clear` |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | Evaluations complete; heal | IN_CODE | |
| OpenAI shard fail | Merge partial; fill/seal | IN_CODE | |
| scored_ratio below floor | RuntimeError if creative_delivery + framing on | IN_CODE | `_assert_gap_evaluations_complete` |
| voice_ref pending | Incomplete → pin missing_framing | IN_CODE | heal_routing / stage_completion |
| identical | `missing_framing batch_fill` fingerprint | IN_CODE | identical_failures |

## 5. Side effects

- Writes: gap_evaluations.json; sync analysis state — `IN_CODE`
- May open/consume G-VoiceRef / pickup speaker — `IN_CODE` gap_vo_gates
- Consumers: confirm, gap_framing_compose, air/nugget/refinement — contract

## 6. Complexity traps

- OpenAI control + deterministic fill/seal ladder — `IN_CODE`
- Multi-pass coverage CAP=2 — `IN_CODE`
- Gate stack + eligibility hard-stop — `IN_CODE`
- Local heavy ML: Chatterbox voice-ref **orchestration only** (clone quality N/A per §3.4a)

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard plan + boundaries + brief + manifest | Enforced via pipeline/prestage | IN_CODE |
| sufficiency min_rows evaluations≥1 | Skip path may write stub differently | UNKNOWN verify skip artifact |
| remediation volley_retry | Matches ≤2 per shard invoke | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed / schema fail | llm_simple retry ≤2 then fail/fill path | IN_CODE | |
| hollow persist | batch_fill refuses done | IN_CODE | HG-3 |
| retry exhausted | Coverage/fill/seal | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Homunculus `recommended_framing_action` → auto_resolve Yes for hosted; auto pickup/voice path | IN_CODE | `homunculus/gates.py` + `maybe_auto_accept_gap_gate_defaults` |
| human stall required? | Only if auto_resolve blocked (true monologue → skip) or voice_ref must_act | IN_CODE | |
| GUI-only? | Partial without driver needs GUI Yes — Full-auto must not | IN_CODE | partialAcceleratedGuard |
| auto-accept must fire | Homunculus features OR `INTERVIEW_MUX_AUTO_ACCEPT_GATES` / gap_fill.auto_accept_defaults | IN_CODE | defaults: auto_accept_defaults **false**; brain 0.2.0 supplies auto |
| config default auto_accept false | Relies on homunculus_auto — landmine if features off | IN_CODE | |
| partial-only fix risk | Adding must_act for G-Framing under Full-auto | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| analysis.gap_fill.default_framing_enabled | true | recommended Yes |
| analysis.gap_fill.auto_accept_defaults | false | env/homunculus needed |
| analysis.gap_fill.auto_skip_when_ineligible | false | loud fail vs skip |
| analysis.gap_fill.require_explicit_opt_in | true | decision pending until set |
| MISSING_FRAMING_COVERAGE_CAP | 2 | seal after |

## TEST_GAP

- Homunculus features off + Full-auto without AUTO_ACCEPT env (stall)
- Skip stub completeness vs sufficiency claim

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [x] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [x] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Confirm Start Full-auto always enables homunculus features so G-Framing auto-fires without `auto_accept_defaults=true`?

## discovery_status

`complete`
