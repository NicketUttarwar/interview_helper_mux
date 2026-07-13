# Evaluation metrics

**Measurement tools:** `ffprobe` (format/duration) and `ffmpeg` `loudnorm` filter `print_format=json` (`input_i`, `input_tp`) for integrated LUFS and true peak on finished masters (BUILD-070). `pyloudnorm` + `soundfile` measure integrated LUFS on the **assembly bus** before the final limiter (BUILD-071) — [anchored-toolchain.md](./anchored-toolchain.md).

**Structured JSON artifacts:** LLM outputs are validated at the stage boundary (`validate_stage_artifacts`) and on every disk write (`validate_artifact_write`). Semantic completeness (themes, thesis, topics) drives GUI `partial` status and optional pipeline re-run — [artifact-generation-and-validation.md](./artifact-generation-and-validation.md), [json-schema-coverage.md](./json-schema-coverage.md).

## Transcription QC

| Check | Pass heuristic |
|-------|----------------|
| Speaker labels | ≥2 speakers or single-speaker flag |
| Timestamps | Monotonic word times |
| WER | No automated WER in v1; flag if >30% `[inaudible]` tokens |
| Confidence review | Chunks with mean word confidence < 0.85 flagged `needs_review` in queue |
| G0 sign-off | `.stage_done/transcript_review` required before speaker_roles |

## Gap / segment quality

| Check | Rule |
|-------|------|
| Self-explanatory | Every included Flow 1 segment `ready` or has scheduled VO |
| Flow 2 clip | Each highlight self-contained or ≤8s setup VO |

## Audio QA (`verify_master.py`)

| Metric | Flow 1 target | Flow 2 target |
|--------|---------------|---------------|
| Integrated LUFS | −16 ±1 | −14 ±1 (social) |
| True peak | ≤ −1 dBTP | ≤ −1 dBTP |
| Sample rate | 48000 or 44100 | same |
| Duration | > 60s | 60s–180s typical |

**Enforcement (BUILD-070):** `interview_mux.master_qc.verify_master` measures integrated LUFS and true peak; failures list actionable thresholds. CLI (`tools/verify_master.py`) exits non-zero on fail; GUI logs pass/fail on `stage: verify_master` after `flow1` / `flow2` execute.

**Mastering bus (BUILD-071):** `interview_mux.mastering_bus.measure_assembly_bus` runs ITU-R BS.1770 integrated loudness on `assembly.wav` via `pyloudnorm`. `stages/mastering.py` logs the reading, then applies ffmpeg `loudnorm` (true-peak limiter) using flow targets from `master_qc.TARGETS` (−16 / −14 LUFS, −1 dBTP ceiling). Post-export QA still uses BUILD-070 on `master.wav`.

**Noise on master:** If integrated noise or operator listen-test fails, offer [pre-clean](../pipeline/audio_preclean/README.md) and re-run from `mux_flow*` or ingest — not a substitute for proper mix ducking (BUILD-065).

## Flow 1 narrative

- Coverage audit: every `content_brief.topics[]` maps to ≥1 segment or documented exclude
- No chapter with zero segments

**Enforcement:** `interview_mux.narrative_qc.validate_flow1_narrative` checks topic mappings against `coverage_audit.json` and non-empty `selection.json` chapters. CLI (`tools/validate_narrative.py --run-id <exec_id>`) exits non-zero on fail. Pipeline warns before `full_master_ranking` and `edl` (`gui_log.jsonl`, `detail: narrative_qc_pass|narrative_qc_fail`); set `narrative_qc.strict: true` in config to block.

## Flow 1 EDL narrative

| Check | Rule |
|-------|------|
| Selection parity | EDL speech clips match final `selection.ordered_segment_ids`; excluded segments do not appear |
| Coverage survival | Covered topics and claims still have represented speech clips after NLE / EDL build |
| Chapter continuity | Each selection chapter appears in the EDL without unrelated clips splitting it |
| Ordering constraints | `narrative_plan.ordering_constraints` are respected in final speech order |
| Transitions | `transitions.json` adjacent pairs map to transition clips in `edl.json` |
| Gap placements | `gap_report` record lines targeting selected segments have VO clips / `gap_placements` or documented missing-VO warnings |
| Flagship audit | `edl_narrative_audit.json` has no blocking issues |

**Enforcement:** `interview_mux.edl_narrative_qc.validate_flow1_edl_narrative` runs from `edl` after EDL construction and before `edl.json` is written. `edl_narrative_qc.strict: true` blocks on failures and records `run_meta.qc_summaries.edl_narrative_qc`. CLI: `tools/validate_narrative.py --run-id <exec_id> --include-edl`.

### Flow 3 show description

**Enforcement:** `interview_mux.show_notes_qc.validate_show_description` checks `evidence_segment_ids`, hook/body alignment, word count tolerance, and key-claim coverage. CLI: `tools/validate_show_description.py --run-id <exec_id>`. Pipeline warns on persist (`show_notes_qc_fail`); set `show_notes_qc.strict: true` to block bad artifacts.

## Flow 2 highlights

- ≤5 clips, non-overlapping source ranges
- At least one clip tagged as headline in selection JSON
- Highlight `scores` must include `diversity_bonus` (schema-validated)

## Prompt / artifact QA

- After each LLM stage, `interview_mux.prompt_validation.validate_stage_artifacts` checks `artifacts` against `docs/cross-cutting/json-schemas/artifacts/*.schema.json`
- Failed validation triggers one automatic retry with error feedback in the message volley
- Golden fixtures: `tests/fixtures/prompts/` (optional regression snapshots)

**Operator workflow:** [operator-stage-checklists.md](../workflows/operator-stage-checklists.md) · **When something breaks:** [troubleshooting.md](../workflows/troubleshooting.md) · **Config caps / keys:** [config-keys.md](./config-keys.md)
