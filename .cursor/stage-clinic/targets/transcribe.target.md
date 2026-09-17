# Target Spec — transcribe

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| Apple Silicon + local_speech + `ingest/normalized.wav` | write `transcript/full.json` + `speakers.json` → mark_done | Completes unattended |
| missing normalized.wav | hard refuse (`artifact_exists_required`) — no done | Honest halt / heal pin ingest |
| non-Apple Silicon | `RuntimeError` — no hollow done | Hard stop (host env prerequisite) |
| local_speech venv missing | `RuntimeError` — no hollow done | Hard stop until bootstrap |
| `LocalRuntimeUnavailable` / STT fail | `RuntimeError` — no mark_done | Honest halt; host rerun |
| STT returns empty `words` | **target:** incompleteness / refuse — not success-done | Prefer honest pin over G0 babysit (see TR-B4) |
| source_profile / source_card refresh throws | fail-open **after** mark_done | Continues seed walk |
| mid-write before mark_done | incompleteness via primary `transcript/full.json` | Host rerun |

## Rules set (prefer deterministic)

- admit / when arm64 + speech_available + normalized.wav present
- refuse / non-ARM; refuse / missing speech venv; refuse / missing normalized; refuse / LocalRuntimeUnavailable
- wait_for_gate / never on this stage (G0 is next stage)
- incomplete / never mark_done without primary `transcript/full.json` written this pass
- precise invalidate / none declared (ingest clear forces re-STT)
- auto_resolve_default / N/A — env bootstrap is operator/machine, not a gate answer

## Complexity subtraction list

- Contract `remediation.strategies: volley_retry` — no OpenAI; host local-STT `full_stage_rerun` only
- Contract lifecycle `llm_execute` on a local-STT process stage (claim noise)
- Ownership primary producer=`transcribe` for `protected_zones.json` / `speaker_flows.json` while `audio_probes.py` writes them
- Ownership producer=`transcribe` for `diarization_repairs.json` while `diarization_suspicion.py` writes (later probe/G0 path)

## Contract / dependency deltas (proposed; not applied)

- Drop `volley_retry` from `transcribe.yaml`; keep host rerun
- Soft inputs stay `[]`; hard `ingest/normalized.wav` stays enforced
- Reassign ownership primary producers for probe-written transcript sidecars to `audio_probe_build` (or dual-write ALLOW that matches code)
- Do **not** deep-change STT model/venv internals (clinic non-goal)

## Non-goals

- MLX STT / diarization quality, latency, device tuning
- Cloud Transcribe revival
- Making non-ARM platforms work
- G0 GUI correction UX (owned by `transcript_review_build`)

## Acceptance checks

- Missing normalized → no `.stage_done/transcribe`
- Non-ARM / missing venv → RuntimeError, no hollow full.json done marker
- LocalRuntimeUnavailable → RuntimeError after error log
- Successful path writes both full+speakers before mark_done
- Contract remediation has no `volley_retry` after TR-B1
- Ownership producers for zones/flows/repairs match actual writers after TR-B3

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| TR-B1 | P1 | unambiguous | Align contract remediation: remove `volley_retry`; host local-STT rerun only | `transcribe.yaml` via dependency data + verify | 2 | no |
| TR-B2 | P2 | unambiguous | Drop process-stage `llm_execute` lifecycle claim noise | contract generator / dependency data | 2 | no |
| TR-B3 | P1 | unambiguous | Ownership: primary producer for `protected_zones` / `speaker_flows` → `audio_probe_build`; `diarization_repairs` → actual writer stage/helper | `artifact_ownership.py` + ownership tests | 2,7 | no |
| TR-B4 | P1 | needs_you | Empty `words` after normalize: keep done (G0/downstream catch) vs incompleteness refuse? | host rule in `run_transcribe` + focused pytest with fixture empty full | 1,2 | yes if refuse loops forever without cap |

## Defaults inventory impact

- Rows touched: add Stage-local landmine — non-ARM or missing `ASSETS/local_speech` hard-stops Full-auto at transcribe (product env constraint; not a clinic model fix)

## target_status

`draft`
