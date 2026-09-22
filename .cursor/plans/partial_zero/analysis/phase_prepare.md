# Phase analysis — prepare

brain: 0.2.0 | mode: partially_accelerated | code_is_king: true  
stages (phases.py): `audio_preclean` · `ingest` · `transcribe` · `transcript_review_build` · `audio_probe_build`  
Partial order note: `PARTIAL_AUTO_PREPARE_UNTIL_G0` = ingest → transcribe → transcript_review_build (preclean deferred until after G0).

## Level 1 — Stage solo

| Stage | Open routes (HEAD) | Thrash? | Notes |
|-------|--------------------|---------|-------|
| `audio_preclean` | Offer / skip / DeepFilter isolated WAV; Partial defers until post-G0 | Low (local ML hang → DP-LOCAL-ML-RETRY) | Skip stamps `preclean/skip.json` (HP-3); hollow unmark via `prepare_outputs_present` |
| `ingest` | Normalize → `ingest/normalized.wav` | Low | G0-locked after review closes |
| `transcribe` | Local STT → `transcript/full.json` | Medium (STT avail / hang) | Same local-ML gap as audit; G0-locked after close |
| `transcript_review_build` | Queue → `transcript/review_queue.json` | Low–med if hollow | HP-2: missing/hollow queue stays on build; incompleteness SSOT |
| `audio_probe_build` | Probe sidecar for journey | Low | Not on Partial-until-G0 slice; runs with full prepare / after |

## Level 2 — Group

- Internal order / done agreement: Seed order in `phases.py`; Partial driver uses `PARTIAL_AUTO_PREPARE_UNTIL_G0` then waits G0. `prepare_outputs_present` + `unmark_hollow_prepare_stages` refuse hollow `.stage_done`. After G0 close, `G0_LOCKED_RERUN_STAGES` blocks surgical re-STT/re-ingest.
- Candidate SIMPLIFY / CUT: None for Partial ironclad — prepare is the G0 feeder. Preclean remains optional offer (not CUT). Local-ML retry is cross-cutting (already packeted), not a prepare-only CUT.

## Level 3 — Handoffs

| Edge | Ready meaning | Cousin risk |
|------|---------------|-------------|
| start → prepare | Interview audio selected (UI) | — |
| prepare → fix_transcript | `transcript/review_queue.json` seed-complete (build not hollow) | HOLLOW_DONE on review_build; heal pin must be gate not rebuild (HP-4) |
| prepare internals | ingest/transcribe outputs present | Hollow prepare unmark loop |

## Level 4 — Junctions

| Junction id | Fact | Callers | Linked DP |
|-------------|------|---------|-----------|
| (none phase-local) | Prepare is linear + optional preclean; no multi-caller seat junction | — | DP-LOCAL-ML-RETRY (STT/DeepFilter host behavior) |

## Decision Packets drafted

- None new from this phase. Local STT/DeepFilter fail order → existing [DP-LOCAL-ML-RETRY](../packets/DP-LOCAL-ML-RETRY.md).

## Partial impact

Partial must reach G0 after ingest+STT only (preclean deferred). Operator must-act is the next phase (`fix_transcript` / G0), not prepare itself. Hollow review_build or wrong heal to rebuild after queue exists would thrash Partial — HP-4 + prepare_outputs cover HEAD.
