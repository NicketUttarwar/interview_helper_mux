# Possibility Map — air_script_seams

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- delivery #50 | primary `mastering/mastering_plan.json`
- module: `air_script.py::run_air_script_seams` → `compose_pass_b` + `attach_sonic_scenes` + VO contract sync
- contract tier llm_full vs port non_llm / no OpenAI — CODE_DOC_CONFLICT
- flag: `mastering.air_script.enable` default true

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| enable=false | early return (no heal in body) | IN_CODE | `air_script_enabled` |
| plan present | Pass B montage + omits + sonic scenes | IN_CODE | `compose_pass_b` |
| VO contract remaining | restore plan + stamp drift + raise | IN_CODE | `sync_vo_contract_after_layup` |
| soft freeze | compose_pass_b frozen no-op | IN_CODE | `seat_mutation_allowed` |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| compose prior plan | snapshot/restore on drift | IN_CODE | `_snapshot_mastering_plan` |
| gap/selection | used for seats/omits | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| no G* | N/A | IN_CODE | |
| soft freeze | no-op return existing plan | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | clear drift; `heal_or_refuse_mark` | IN_CODE | |
| VO contract drift | restore + stamp + raise | IN_CODE | HF-2 |
| other compose crash | stamp refuse sidecar + raise | IN_CODE | |
| enable off | silent return | IN_CODE | FULL_AUTO_REGRESSION_RISK if seed expects done |

## 5. Side effects

- Mutates mastering_plan (+ gap omits via persist) — IN_CODE
- May write gap_framing_plan (contract) — DOC_ONLY_UNVERIFIED
- Consumers: transitions / music / edl — contract

## 6. Complexity traps

- VO contract ladder thrash — IN_CODE
- Soft freeze no-op vs expected seam rewrite — IN_CODE
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| tier llm_full | deterministic Pass B | CODE_DOC_CONFLICT |
| hard mastering_plan | used | IN_CODE |
| sufficiency beats min 0 | allow empty | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A no OpenAI | | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto defaults (enable=true) | Pass B; heal; no human | IN_CODE | |
| human stall? | No | IN_CODE | |
| enable=false | early return — seed honesty risk | FULL_AUTO_REGRESSION_RISK | `air_script_enabled` |
| drift | hard fail (good) | IN_CODE | |
| partial-only fix risk | don't soft-swallow drift | IN_CODE | |

## Flags (§5.5)

- `mastering.air_script.enable` default true
- `mastering.air_script.fail_open` (compose family; seams still raises on drift)

## TEST_GAP

- enable=false done-marker honesty
- soft-freeze no-op + heal

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Retier contract to process/deterministic?

## discovery_status

`complete`
