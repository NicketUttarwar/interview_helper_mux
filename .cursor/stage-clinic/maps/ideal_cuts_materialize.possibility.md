# Possibility Map — ideal_cuts_materialize

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index (copy from dossier when filled)

- tier: process (contract) / process body `IN_CODE` — no OpenAI
- primary: `understanding/ideal_cuts_materialized.json`
- gate adjacency: none
- LLM class: none (process snap + optional boundary publish)
- seed: 13 analysis

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | Contract hard=`[]`; body requires `understanding/ideal_cuts.json` then snaps | `CODE_DOC_CONFLICT` | `ideal_cuts.py:run_ideal_cuts_materialize` L1064-1082 |
| hard missing | `RuntimeError` if ideal_cuts absent (not soft skip) | `IN_CODE` | `ideal_cuts.py:1064-1065` |
| soft missing | transcript/wav optional → empty/`None`; snap still runs | `IN_CODE` | `ideal_cuts.py:1067-1081` |
| soft stale | No freshness hash gate in body | `UNKNOWN` | — |
| hollow `{}` / `[]` | Empty snap demotes bind_mode; still writes materialized + heals done | `IN_CODE` | `ideal_cuts.py:1087-1096`, `1188-1190` |
| schema-valid semantic junk | Coarse bind rejected → retract boundaries; materialize still completes | `IN_CODE` | `ideal_cuts.py:1109-1141` |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | Consumes `ideal_cuts_propose` artifact | `IN_CODE` | `IDEAL_CUTS_REL` |
| producer invalidated | No stage-local invalidate of propose | `IN_CODE` | contract `invalidates_stages: []` |
| epoch / delivery drift | N/A analysis seed | `IN_CODE` | — |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gate open / waiting | N/A — no journey gate | `IN_CODE` | — |
| gate answered | N/A | `IN_CODE` | — |
| illegal skip | N/A | `IN_CODE` | — |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | Snap + optional `segments/boundaries.json` + seed; heal mark | `IN_CODE` | `ideal_cuts.py:1127-1190` |
| soft fail | Quality-eval exception → skip bind, still complete | `IN_CODE` | `ideal_cuts.py:1129-1142` |
| hard fail | Missing ideal_cuts raises | `IN_CODE` | `ideal_cuts.py:1064-1065` |
| partial persist | May write materialized without boundaries/seed | `IN_CODE` | `wrote_boundaries` / deferred seed stub L1166-1172 |
| done-without-primary | `enable=false` writes hollow disabled doc then heal | `IN_CODE` | `ideal_cuts.py:1056-1061` |
| retry / heal loop | `heal_or_refuse_mark(..., force=True)` | `IN_CODE` | `ideal_cuts.py:1189-1190` |
| identical halt | Not stage-local | `UNKNOWN` | thrash rails cross-cutting |

## 5. Side effects

- Writes (actual): `understanding/ideal_cuts_materialized.json`; optional `understanding/ideal_cuts_selection_seed.json`; optional `segments/boundaries.json` (`IN_CODE` ownership co-ALLOW)
- Forbidden writes risk: retracts own boundaries only via `retract_own_boundaries` (`IN_CODE`)
- Invalidates: contract none; downstream skip paths when bound (`DOC` claim / `IN_CODE` consumers)
- Consumers: `boundary_detection`, `segment_classification`, ranking seed refresh (`IN_CODE`)

## 6. Complexity traps

- OpenAI/external control vs rules: none — deterministic snap
- Multi-heal / caps: force heal after write
- Dual SSOT: boundaries co-owned with `boundary_detection` / resplit / fuse (`IN_CODE` ownership)
- Local heavy ML: N/A (optional wav for acoustic edge refine only; not local-ML clinic scope)

## 7. Contract honesty (declared-vs-actual)

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard inputs `[]` | Raises without `ideal_cuts.json` | `CODE_DOC_CONFLICT` |
| soft ideal_cuts / transcript / wav / boundaries | Matches optional reads except ideal_cuts treated hard | `CODE_DOC_CONFLICT` |
| outputs materialized + seed + boundaries | Matches; boundaries/seed conditional | `IN_CODE` |
| invalidates / consumers | invalidates empty; consumers match skip/bind graph | `IN_CODE` |
| remediation volley_retry | Process stage — LLM retry N/A | `CODE_DOC_CONFLICT` |

## 8. External service variance (OpenAI / cloud)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM) | Process-only | `IN_CODE` | `run_ideal_cuts_materialize` |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults happy path | `enable=true`, `bind_mode=both`; bind if quality OK else LLM boundary owns | `IN_CODE` | `ideal_cuts_cfg` defaults + `config/app.defaults.json` analysis.ideal_cuts |
| human stall required? | No | `IN_CODE` | — |
| GUI-only action dependency? | No | `IN_CODE` | — |
| auto-accept / default must fire | N/A gate | `IN_CODE` | — |
| partial-only fix risk | Tightening bind quality must not force human at this stage | `FULL_AUTO_REGRESSION_RISK` | — |

### §5.5 Flags (defaults)

- `analysis.ideal_cuts.enable` default true — `ideal_cuts.py:ideal_cuts_cfg`
- `bind_mode` default `both` — same
- `skip_boundary_llm_when_bound` / `skip_topic_resplit_when_bound` / `skip_classification_llm_when_bound` default true

### §5.6 TEST_GAP

- Covered: `tests/test_ideal_cuts.py` + ownership/parity (~14 files)
- Gaps: soft-stale upstream; identical-halt interaction; hollow cuts with `prefer_seed_over_shape` under Full-auto

## DoD threats (tag which §0.2 checks this stage threatens)

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

Top footgun: empty/coarse snap still marks done while optionally publishing (or retracting) the shared boundaries SSOT — poisons boundary_detection skip vs LLM choice.

## Open questions for operator

1. Should missing `ideal_cuts.json` be hard refuse (current) or soft hollow-done? (contract says soft)

## discovery_status

`complete`
