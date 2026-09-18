# Possibility Map — mastering_research_waves

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process (contract) / body = deterministic probes — `IN_CODE` `mastering_research.py::run_mastering_research_waves`
- primary: `mastering/research/waves.json` + `mastering/research/<field_id>.json`
- upstream: routing stage (contract hard); body does not read it
- downstream: `mastering_research_rollup`
- gate: none | LLM: none | thrash: no | tests: thin (HM-1 schema)

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | Probe WAVE_FIELDS; write waves + field reports; heal | IN_CODE | `run_mastering_research_waves` |
| hard missing (`routing.json`) | Still runs — hard:[] (MRW-B1) | IN_CODE | contract soft probes only |
| soft missing (delivery artifacts) | Field `skipped_or_thin`; stage succeeds | IN_CODE | `_probe` / `FIELD_PROBES` |
| soft stale | No freshness refuse | IN_CODE | |
| hollow primary | HM-1 schema incompleteness blocks done | IN_CODE | `_mastering_schema_hollow_incompleteness` |
| schema-valid semantic junk | Thin fields (confidence 0.2) still OK | IN_CODE | `write_field_report` |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | Proceed | IN_CODE | seed admit |
| producer invalidated | Re-run when cleared | IN_CODE | lifecycle |
| epoch / delivery drift | Soft probes thin until delivery exists (expected at analysis) | IN_CODE | `_probe` |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gate open / waiting | N/A | IN_CODE | |
| gate answered | N/A | IN_CODE | |
| illegal skip | N/A | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | waves.json + field reports; force heal | IN_CODE | `_heal_research_stage` |
| soft / hard fail | IO only | IN_CODE | |
| partial persist | Per-field writes before waves.json | IN_CODE | `run_research_wave` |
| done-without-primary | Refused by HM-1 | IN_CODE | `stage_completion` |
| retry / heal / identical | Force heal; no identical fingerprint | IN_CODE | |

## 5. Side effects

- Writes: `mastering/research/waves.json`, `mastering/research/*.json` — `IN_CODE`
- Ownership: ALLOW rows for waves + glob — `IN_CODE` `artifact_ownership.py`
- Invalidates: none explicit; rollup re-probes same fields — `IN_CODE`
- Consumers: `mastering_research_rollup` (`run_research_rollup` also re-runs waves)

## 6. Complexity traps

- OpenAI: none
- Dual SSOT / duplicate work: rollup re-runs all waves — `IN_CODE` (**MRW-B2 documented** in `run_mastering_research_waves` / `run_research_rollup` docstrings — intentional fail-open refresh, shared `run_research_wave`)
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard routing.json | hard:[] — not read | IN_CODE |
| soft delivery paths | Probe-only thin | IN_CODE |
| outputs waves + research/ | Matches | IN_CODE |
| remediation volley_retry | No LLM | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A (no external LLM) | — | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults happy path | Completes; many fields thin pre-delivery | IN_CODE | |
| human stall required? | No | IN_CODE | |
| GUI-only action dependency? | No | IN_CODE | |
| auto-accept / default must fire | N/A | IN_CODE | |
| partial-only fix risk | None | IN_CODE | |

## Flags (§5.5)

- none stage-local (shared WAVE_FIELDS catalog only)

## TEST_GAP (§5.6)

- routing hard-input ignored vs contract (MRW-B1 needs_you)
- intentional duplicate probe with rollup — documented in code docstrings (MRW-B2)

## DoD threats

- [ ] 1 Progression  [ ] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions for operator

1. Align routing hard claim with body (require vs demote to soft)?

## discovery_status

`complete`
