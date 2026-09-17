# Possibility Map — gap_framing_recompose

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: deterministic | seed **#48** | primary `understanding/gap_framing_recompose.json`
- module: `refinement_passes.py::run_gap_framing_recompose`
- default Full-auto: layup authority thin adapter (republish) — not LLM like compose
- lifecycle llm_execute / VO_REGISTER misleading — `CODE_DOC_CONFLICT`
- Local heavy ML: N/A | OpenAI: N/A on default path

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| authority + plan | republish gap_report → accept sidecar | IN_CODE | `authoritative_gap_report` path |
| seat freeze | skip stub + heal without agenda | IN_CODE | |
| contract hard agenda | Soft | CODE_DOC_CONFLICT | |
| gap unsanitary | refuse stub + raise | IN_CODE | `_finish_pass2` |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| after agenda/sanitize | Seed | IN_CODE | |
| FREEZE_STICKY | Seed sticky under hard freeze+edl | IN_CODE | seed_policy |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| G1 | Optional after accept/skip — not wait here | IN_CODE | |
| seat freeze | Intentional no-op | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| authority happy | sidecar accept + heal | IN_CODE | |
| unsanitary | refuse resume recompose | IN_CODE | |
| legacy activate | deterministic filter (no OpenAI) | IN_CODE | |

## 5. Side effects

- Primary sidecar; may rewrite gap_report; skip_copy — `IN_CODE`
- Contract consumers/invalidates empty — `DOC incomplete`

## 6. Complexity traps

- Dual path authority vs legacy activate — `IN_CODE`
- Duplicate seat-gate at top — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| lifecycle llm_execute | No LLM default | CODE_DOC_CONFLICT |
| hard agenda | Soft / skip without | CODE_DOC_CONFLICT |
| consumers [] | Mutates gap_report → VO/EDL | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A default Full-auto | — | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | authoritative_gap_report=true → republish adapter; no human | IN_CODE | |
| human stall? | No (unsanitary loops only) | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Dual seat-gate; empty contract consumers; freeze sticky | IN_CODE | |
| partial-only fix risk | Re-enable LLM recompose; clear freeze sticky | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

- `nugget_layup.authoritative_gap_report` default true
- `refinement_passes.enabled` / whitelist

## TEST_GAP

- Layup-authority happy path unit; HF-5 refuse after publish

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [x] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [x] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Retire legacy non-layup activate path?
2. Fill contract consumers?

## discovery_status

`complete`
