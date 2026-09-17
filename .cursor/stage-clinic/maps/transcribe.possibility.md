# Possibility Map — transcribe

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process / local MLX STT+diarization — `IN_CODE`
- primary: `transcript/full.json` (+ `transcript/speakers.json`) — `IN_CODE`
- gate adjacency: feeds G0 build — `IN_CODE`
- LLM: local-heavy only (skip deep dive)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | Requires `ingest/normalized.wav` | IN_CODE | `artifact_exists_required` |
| hard missing | raises / required check | IN_CODE | |
| soft missing | N/A soft [] | IN_CODE | |
| soft stale | N/A | IN_CODE | |
| hollow | empty words still mark_done if normalize returns | IN_CODE | success log uses len(words) |
| semantic junk | STT garbage passes as JSON | IN_CODE | host does not semantic-gate |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | reads normalized | IN_CODE | |
| producer invalidated | ingest clear forces re-STT | IN_CODE | |
| epoch drift | N/A | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gate open | none on this stage | IN_CODE | |
| gate answered | N/A | IN_CODE | |
| illegal skip | cannot skip | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | write full+speakers → mark_done | IN_CODE | `run_transcribe` |
| soft fail | none; LocalRuntimeUnavailable → RuntimeError | IN_CODE | |
| hard fail | non-Apple Silicon / missing speech venv / STT fail | IN_CODE | |
| partial persist | write then fail before mark possible | UNKNOWN | |
| done-without-primary | mark after writes; prepare_outputs requires full.json | IN_CODE | |
| retry / heal | host | IN_CODE | |
| identical halt | UNKNOWN | UNKNOWN | |

## 5. Side effects

- Writes: `transcript/full.json`, `transcript/speakers.json`; source_profile / source_card fail-open — `IN_CODE`
- Ownership: protected_zones/speaker_flows listed under transcribe producers but written by audio_probe (operational mode allows) — `CODE_DOC_CONFLICT`
- Invalidates: none declared
- Consumers: G0 build, probes, SAP, spine, speaker_roles, content_context — `IN_CODE`

## 6. Complexity traps

- OpenAI: none
- Local heavy ML: MLX STT+diarization via `stt_runner` / local_speech venv — N/A internals

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard normalized.wav | enforced | IN_CODE |
| soft [] | true | IN_CODE |
| outputs full+speakers | matches | IN_CODE |
| invalidates [] | true | IN_CODE |
| remediation volley_retry | local STT rerun | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM) | N/A | IN_CODE | |

## 9. Full-auto / defaults path

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults happy path | Requires Apple Silicon + local_speech bootstrap; else hard fail | IN_CODE | `run_transcribe` |
| human stall required? | No (unless machine/venv missing → hard fail) | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| auto-accept | N/A | IN_CODE | |
| partial-only fix risk | None | IN_CODE | |

## DoD threats

- [x] 1 Progression  [ ] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [ ] 7 Cross-stage

*(Progression/defaults: non-ARM or missing local_speech hard-stops unattended Full-auto — host env, not clinic model quality.)*

## Open questions for operator

1. _(none for clinic; env prerequisite is product constraint)_

## discovery_status

`complete`
