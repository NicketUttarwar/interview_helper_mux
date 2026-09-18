# Possibility Map — ideal_cuts_propose

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full OpenAI — `IN_CODE`
- primary: `understanding/ideal_cuts.json` — `IN_CODE`
- gate adjacency: none — `IN_CODE`
- LLM: `understanding/ideal-cuts-propose.system.txt`

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | requires talking_points.json (RuntimeError if missing); transcript compacted | IN_CODE | `build_input` |
| hard missing talking_points | hard fail | IN_CODE | |
| soft brief/speakers | optional | IN_CODE | |
| disabled ideal_cuts | stub cut + heal force | IN_CODE | |
| hollow cuts | schema min_rows; persist may redistribute span | IN_CODE | |
| clustered cuts long tape | redistribute or RuntimeError if span < floor | IN_CODE | persist gate |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | after talking_points | IN_CODE | |
| producer invalidated | [] declared | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all | none | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | persist after span check → mark | IN_CODE | |
| soft fail | not fail_open | IN_CODE | |
| hard fail | StageError; persist RuntimeError span (retryable as schema-like in llm_simple) | IN_CODE | llm_simple persist RuntimeError retry |
| hollow persist | schema + span floor on ≥15min; span fail → StageError after ≤2 (ICP-B4) | IN_CODE | llm_simple |
| disabled stub | placeholder cut | IN_CODE | |

## 5. Side effects

- Writes: ideal_cuts.json — `IN_CODE`
- Consumers: materialize, boundary, nugget corpus — contract

## 6. Complexity traps

- OpenAI + host redistribute_clustered_cuts
- Disable stub
- Soft probes via transcript_quality (kept; ICP-B1 prune skipped)

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard transcript+talking_points | talking_points enforced; transcript read | IN_CODE |
| soft brief/speakers + transcript_quality probes | optional; build_input reads all | IN_CODE |
| outputs ideal_cuts schema | matches | IN_CODE |
| invalidates [] | true | IN_CODE |

## 8. External service variance (OpenAI)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed/schema | ≤2 then raise | IN_CODE | |
| retry exhausted | StageError | IN_CODE | |
| hollow persist | blocked | IN_CODE | |
| span fail after accept | RuntimeError retryable once; attempt 2 → StageError (ICP-B4) | IN_CODE | llm_simple persist handler |

## 9. Full-auto / defaults path

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto defaults | enable=true → OpenAI propose + span gate on long interviews; floor 0.45 in app.defaults (ICP-B2) | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| partial-only fix risk | lowering span floor only for partial would diverge masters | FULL_AUTO_REGRESSION_RISK | |

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [ ] 7 Cross-stage

## Open questions for operator

1. ICP-B3: enable=false stub force-done vs incompleteness refuse?

## discovery_status

`complete` — Wave 2 ICP-B2/B4 patched; ICP-B1 skipped (probes used); ICP-B3 open
