# Possibility Map — transcript_review_build

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process / deterministic clip ranking — `IN_CODE`
- primary: `transcript/review_queue.json` — `IN_CODE`
- gate adjacency: **arms G0** (`transcript_review` must-act) — `IN_CODE`
- LLM: none

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | requires `transcript/full.json` + `ingest/normalized.wav` | IN_CODE | `run_transcript_review_build` |
| hard missing | artifact_exists_required raises | IN_CODE | |
| soft missing | speakers soft unused in build body | IN_CODE | contract soft speakers |
| soft stale | N/A | IN_CODE | |
| hollow `{}` | validate_transcript_review_queue; empty chunks allowed by HP-2 incompleteness | IN_CODE | `_transcript_review_build_incompleteness` |
| semantic junk | low-quality ranks still schema-ok | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | reads committed full.json (also helpers for staged pending) | IN_CODE | `_read_transcript_full` helpers |
| producer invalidated | rebuild regenerates clips | IN_CODE | |
| epoch drift | N/A | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gate open / waiting | After build, G0 pending until operator/driver complete | IN_CODE | `gates.check_transcript_review_pending` |
| gate answered | `mark_transcript_review_complete` applies corrections + mark_done transcript_review | IN_CODE | |
| illegal skip | `maybe_auto_complete_transcript_review` **always False** in stage body; Full-auto driver `complete_g0` posts accept_unreviewed; Partial must wait | IN_CODE | body + `tools/full_auto_driver.complete_g0` |
| Homunculus seed | `transcript_review` stage raises g0_pending — driver owns complete | IN_CODE | `pipeline._run_single_stage_impl` |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | queue + clips + empty corrections → mark_done build | IN_CODE | |
| soft fail | none | IN_CODE | |
| hard fail | schema fail SystemExit; missing inputs | IN_CODE | |
| partial persist | clips dir cleared then rewritten | IN_CODE | |
| done-without-primary | incompleteness blocks heal if queue missing/invalid | IN_CODE | HP-2 |
| retry / heal | heal_or_raise path via incompleteness | IN_CODE | |
| identical halt | UNKNOWN | UNKNOWN | |

## 5. Side effects

- Writes: `transcript/review_queue.json`, `transcript/corrections.json` (empty), `transcript/review_clips/*.wav` — `IN_CODE`
- Invalidates: G0 complete may `clear_from(speaker_roles)` if roles already done — `IN_CODE`
- Consumers: G0 GUI / gate; downstream soft-read review_queue — contract

## 6. Complexity traps

- OpenAI: none
- Dual SSOT: StageInfo lists audio_probe before G0 build but ANALYSIS_ORDER has review_build then probe — `CODE_DOC_CONFLICT` (`web/stages.py` PRE_G0 vs `v2/config.py`)
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard full.json | enforced (+ normalized required in code though soft in contract) | CODE_DOC_CONFLICT |
| soft speakers+normalized | normalized treated hard in body | CODE_DOC_CONFLICT |
| outputs queue+corrections+clips | matches | IN_CODE |
| consumers transcript_review | gate id | IN_CODE |
| remediation volley_retry | host rebuild | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM) | N/A | IN_CODE | |

## 9. Full-auto / defaults path

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults happy path | Build completes; driver `complete_g0` auto-accepts unreviewed | IN_CODE | `complete_g0` |
| human stall required? | Partial: yes (MUST_ACT). Full-auto: no if driver armed | IN_CODE | |
| GUI-only? | Partial GUI review; Full-auto API accept | IN_CODE | |
| auto-accept must fire | Full-auto driver must call complete; body does not auto-close | IN_CODE | `maybe_auto_complete` returns False |
| partial-only fix risk | Do not auto-close G0 in body for partial | FULL_AUTO_REGRESSION_RISK | |

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [x] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [ ] 7 Cross-stage

## Open questions for operator

1. _(none — G0 full-auto vs partial split is encoded)_

## discovery_status

`complete`
