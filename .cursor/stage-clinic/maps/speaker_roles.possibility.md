# Possibility Map — speaker_roles

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full / OpenAI via `run_analysis_llm_stage` — `IN_CODE`
- primary: `understanding/speakers.json` — `IN_CODE`
- gate adjacency: post-G0 (seed); G0 complete may clear this stage — `IN_CODE`
- LLM: OpenAI prompt `understanding/speaker-roles.system.txt` (+ local framer prep N/A)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | reads transcript/full + transcript/speakers samples | IN_CODE | `run_speaker_roles` build_input |
| hard missing | read_json fails | IN_CODE | |
| contract hard spine when enabled | **body does not require spine**; optional attach absent here | CODE_DOC_CONFLICT | contract vs `understanding.py` |
| soft diarization_repairs | optional attach | IN_CODE | |
| hollow speakers | schema + sufficiency min_rows / not_all_unknown (contract claim; validate_stage_artifacts) | IN_CODE | |
| semantic junk | schema-valid wrong roles poison topology | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | after spine in seed | IN_CODE | |
| G0 rewind | mark complete clears speaker_roles if done | IN_CODE | `mark_transcript_review_complete` |
| dispatch_delta | stage has hard-input hash pins | IN_CODE | `dispatch_delta.py` speaker_roles |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| G0 open | later analysis should wait; runner calls maybe_auto_complete (no-op) before non-prepare stages | IN_CODE | pipeline |
| illegal skip | none | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | persist enrich_speakers → mark_done via llm_simple | IN_CODE | |
| soft fail | attempt2 non-blocking needs may accept; diarization fallback speakers | IN_CODE | `llm_simple` speaker_roles branches |
| hard fail | StageError after ≤2 attempts if not accepted | IN_CODE | max 2 |
| hollow persist | validate_stage_artifacts before persist; fail_open_partial **not** in set for speaker_roles | IN_CODE | `_FAIL_OPEN_PARTIAL_STAGES` |
| retry / heal | ≤2 then raise | IN_CODE | |
| identical halt | recovery_controller special-case speaker_roles | IN_CODE | `recovery_controller.py` |

## 5. Side effects

- Writes: understanding/speakers.json; may enrich content_brief from evidence fail-open — `IN_CODE`
- Invalidates (contract): content_context, boundary, segment_classification, source_topology_build — verify live invalidate on rewrite — `UNKNOWN`/`DOC_ONLY` until ADG call site cited; contract claim
- Consumers: topology hard, content_context hard — `IN_CODE`

## 6. Complexity traps

- OpenAI control: stratified samples + talk stats + evidence packet; fallback on locked diarization need
- Local framer: prepare_volley_for_llm fail-open — N/A
- Multi-heal: recovery_controller pins

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard transcript + spine(when) | spine not enforced in body | CODE_DOC_CONFLICT |
| soft transcript speakers + repairs | used | IN_CODE |
| outputs speakers.json schema | matches | IN_CODE |
| sufficiency speakers rules | schema path via prompt_validation | IN_CODE |
| remediation volley_retry | matches ≤2 | IN_CODE |

## 8. External service variance (OpenAI)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed JSON | retry then StageError / fallback path | IN_CODE | `llm_simple` |
| schema fail | retry note + attempt 2; then raise | IN_CODE | |
| retry exhausted (≤2) | StageError | IN_CODE | |
| hollow persist | blocked by validate unless fallback artifact | IN_CODE | |
| status!=complete needs | may demote unfulfillable diarization needs; mixed fallback | IN_CODE | |

## 9. Full-auto / defaults path

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto happy path | OpenAI key required; 1–2 attempts → speakers.json | IN_CODE | |
| human stall? | No journey gate | IN_CODE | |
| GUI-only? | editable speakers but not required | IN_CODE | |
| auto-accept | N/A | IN_CODE | |
| partial-only fix risk | fallback roles must remain Full-auto-safe | FULL_AUTO_REGRESSION_RISK | |

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [x] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions for operator

1. Should spine remain a hard contract input when the body never reads it?

## discovery_status

`complete`
