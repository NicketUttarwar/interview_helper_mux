# Target Spec — source_acoustic_profile

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| hard `ingest/normalized.wav` + `transcript/full.json` present | derive pacing/energy/mix_contract → write profile → mark_done | Completes unattended |
| `preclean/isolated.wav` present | energy metrics from isolated; lineage records preclean | Completes (prefer isolated for energy) |
| isolated missing | energy from normalized; preclean lineage null | Completes |
| empty / no timed words | write schema-valid calm defaults (`pace_class=calm`) + done | Completes — honest empty-tape profile (not hollow `{}`) |
| missing hard audio or transcript | hard fail on read — no done | Honest halt |
| schema-invalid / missing primary after “done” | `_source_acoustic_profile_incompleteness` (HU-1) heals | Host pin resume |
| prior `operator_overrides` present | preserve overrides across recompute | Full-auto: no GUI required; edits optional |
| `write_source_readiness` throws | warn fail-open **after** mark_done | Continues seed walk |

## Rules set (prefer deterministic)

- admit / when normalized.wav + transcript/full.json readable
- refuse / missing hard inputs (raise on read)
- wait_for_gate / never
- incomplete / missing or schema-hollow primary JSON (HU-1) — never treat `{}` as done
- precise invalidate / none from this stage
- auto_resolve_default / N/A — optional GUI edits must not block seed walk

## Complexity subtraction list

- Contract soft `understanding/interview_spine.json` — unused by `run_source_acoustic_profile` derive path
- Contract `remediation: volley_retry` — deterministic host stage; no LLM
- Contract lifecycle `llm_execute` claim noise on deterministic tier
- Contract listing `source_readiness.json` as stage output while ownership producer=`ops` and write is fail-open helper (claim vs ownership mismatch)
- Thrash-hardening membership for SAP — stage is deterministic non-thrash; keep only if heal evidence requires it

## Contract / dependency deltas (proposed; not applied)

- Drop soft spine input (or mark truly optional unused) via dependency data
- Drop `volley_retry`; keep `full_stage_rerun`
- Prefer readiness as side-effect / ops artifact, not SAP primary outputs row — or dual-document helper write after committed
- Keep hard inputs as today; soft preclean stays optional prefer for energy

## Non-goals

- Numpy/wave metric quality tuning (WPM thresholds, pace_class heuristics)
- Requiring GUI approval of SAP before seed advance
- Changing empty-word calm-default policy (upstream empty STT is TR-B4)
- Local heavy ML (none)

## Acceptance checks

- Missing hard input → no `.stage_done/source_acoustic_profile`
- Empty words → schema-valid profile with `pace_class=calm`, incompleteness None
- Isolated present → `derived_from.preclean_isolated` set; energy path uses isolated file
- HU-1: `{}` / schema fail → incompleteness string; heal resumes stage
- After SAP-B1: contract remediation has no `volley_retry`
- Full-auto path never waits on editable StageInfo

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| SAP-B1 | P1 | unambiguous | Align contract remediation: remove `volley_retry` | dependency data + verify | 2 | no |
| SAP-B2 | P2 | unambiguous | Drop `llm_execute` lifecycle noise on deterministic SAP | contract generator | 2 | no |
| SAP-B3 | P1 | unambiguous | Remove unused soft `interview_spine.json` from SAP contract inputs | dependency data + stage_input_checks unchanged | 2 | no |
| SAP-B4 | P2 | unambiguous | Align readiness: drop from SAP `outputs` **or** ownership primary if stage must own post-commit write | ownership + contract verify | 2,7 | no |
| SAP-B5 | P3 | answered | Not a thrash hotspot (2B); KEEP in FORCE_DONE_GUARDED for HU-1 hollow honesty | comment + dossier | 7 | no |

## Defaults inventory impact

- Rows touched: none (no gate/stall/default landmine; empty-word calm defaults are intentional host behavior)

## target_status

`draft` — Wave 2 applied SAP-B1–B4; SAP-B5 **2B** (false thrash hotspot; KEEP FORCE_DONE)
