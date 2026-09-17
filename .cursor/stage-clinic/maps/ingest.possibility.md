# Possibility Map — ingest

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process / ffmpeg normalize+loudness — `IN_CODE`
- primary: `ingest/normalized.wav` — `IN_CODE`
- gate adjacency: none (after preclean) — `IN_CODE`
- LLM: none

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | No hard; prefers `preclean/isolated.wav` else `input_audio()` | IN_CODE | `_ingest_source` |
| hard missing | N/A | IN_CODE | |
| soft missing | Missing isolated → raw input; missing input → FileNotFoundError | IN_CODE | `run_ingest` |
| soft stale | Always re-ffmpeg; checksums rewritten | IN_CODE | |
| hollow | N/A WAV | IN_CODE | |
| semantic junk | Corrupt input fails ffmpeg | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | Uses isolated if file present regardless of preclean done marker | IN_CODE | `_ingest_source` |
| producer invalidated | Preclean accept clears ingest via clear_from | IN_CODE | audio_preclean invalidate |
| epoch drift | N/A early analysis | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gate open / waiting | none | IN_CODE | |
| gate answered | N/A | IN_CODE | |
| illegal skip | Cannot skip; required seed stage | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | ffmpeg → loudness.json + checksums → mark_done | IN_CODE | `run_ingest` |
| soft fail | source_profile / readiness fail-open warnings | IN_CODE | try/except tail |
| hard fail | missing input / ffmpeg failure | IN_CODE | |
| partial persist | possible if crash mid-write | UNKNOWN | |
| done-without-primary | mark_done after normalized written; ownership prepare_outputs requires wav | IN_CODE | |
| retry / heal | host rerun | IN_CODE | |
| identical halt | UNKNOWN | UNKNOWN | |

## 5. Side effects

- Writes: `ingest/normalized.wav`, `ingest/loudness.json`, `ingest/checksums.json`; may refresh source_profile / source_readiness — `IN_CODE`
- Forbidden writes: low — `IN_CODE`
- Invalidates: none declared; consumers re-read wav — `IN_CODE`
- Consumers: transcribe, probes, SAP, topology, mix, master_finalize — contract claim + code reads

## 6. Complexity traps

- OpenAI: none
- Multi-heal: none notable
- Dual SSOT: none
- Local heavy ML: N/A (ffmpeg host)

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard [] | true | IN_CODE |
| soft preclean/isolated | optional prefer | IN_CODE |
| outputs normalized+checksums+loudness | matches | IN_CODE |
| invalidates [] | true | IN_CODE |
| remediation volley_retry | host ffmpeg rerun not LLM | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM) | N/A | IN_CODE | |

## 9. Full-auto / defaults path

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults happy path | After preclean (or raw), ffmpeg loudness stabilize → done | IN_CODE | `run_ingest` + loudness cfg |
| human stall required? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| auto-accept must fire | N/A | IN_CODE | |
| partial-only fix risk | None observed | IN_CODE | |

## DoD threats

- [ ] 1 Progression  [ ] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [ ] 7 Cross-stage

## Open questions for operator

1. _(none)_

## discovery_status

`complete`
