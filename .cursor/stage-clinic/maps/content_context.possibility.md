# Possibility Map — content_context

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full OpenAI — `IN_CODE`
- primary: `understanding/content_brief.json` — `IN_CODE`
- gate adjacency: none — `IN_CODE`
- LLM: `understanding/content-context.system.txt` (+ shard batch path)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | contract hard: speakers+transcript+topology; body refuses without topology before LLM (CC-B1) | IN_CODE | `_content_context_base_payload` + early refuse |
| hard missing | PRESTAGE hard_input_strict default **off** — may run without topology | IN_CODE | `artifact_lifecycle.hard_input_strict` |
| soft missing | quality/spine/adaptation optional | IN_CODE | |
| hollow brief | schema + sufficiency thesis/topics | IN_CODE | |
| semantic junk | schema-valid weak thesis | IN_CODE | |
| long transcript | proactive shard + merge_content_brief_artifacts | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | after topology in seed | IN_CODE | |
| producer invalidated | contract invalidates boundary/classification/… | DOC_ONLY_UNVERIFIED | |
| epoch drift | N/A | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all | none | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | persist make_stage_persist → mark_done | IN_CODE | |
| soft fail | not in fail_open_partial set | IN_CODE | |
| hard fail | StageError ≤2; shard path raises if no parts | IN_CODE | |
| hollow persist | validate_stage_artifacts | IN_CODE | |
| post hooks | value extract / coherence fail-open after done | IN_CODE | |
| identical halt | thrash list includes content_context | IN_CODE | |

## 5. Side effects

- Writes: content_brief.json (+ analysis_state sync) — `IN_CODE`
- Consumers: talking_points, ideal_cuts, boundary, … — contract

## 6. Complexity traps

- OpenAI sharding multi-call then merge (each shard uses llm_simple ≤2)
- Local framer N/A
- Packet denylist via lint_llm_user_payload — `IN_CODE`

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard speakers+transcript+topology | topology refused in body+preflight; speakers via preflight | IN_CODE |
| soft review_queue once via transcript_quality_reads (CC-B2) | no duplicate | IN_CODE |
| outputs content_brief schema | matches | IN_CODE |
| remediation volley_retry | ≤2 | IN_CODE |

## 8. External service variance (OpenAI)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed JSON | retry then StageError | IN_CODE | llm_simple |
| schema fail | retry then raise | IN_CODE | |
| retry exhausted | StageError (no fail-open) | IN_CODE | |
| hollow persist | blocked by schema validate | IN_CODE | |
| shard empty parts | RuntimeError | IN_CODE | |

## 9. Full-auto / defaults path

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto happy path | OpenAI required; long tapes multi-volley | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | editable brief optional | IN_CODE | |
| partial-only fix risk | enforcing topology hard at PRESTAGE could stall soft runs | FULL_AUTO_REGRESSION_RISK | |

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions for operator

1. Align contract hard topology with body (enforce vs soft-attach)?

## discovery_status

`complete`
