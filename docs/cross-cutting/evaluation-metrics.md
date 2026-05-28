# Evaluation metrics

**Measurement tools:** `ffprobe` (format/duration) and `ffmpeg` `loudnorm` filter `print_format=json` (`input_i`, `input_tp`) for integrated LUFS and true peak on finished masters (BUILD-070). `pyloudnorm` + `soundfile` measure integrated LUFS on the **assembly bus** before the final limiter (BUILD-071) — [anchored-toolchain.md](./anchored-toolchain.md).

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

## Flow 2 highlights

- ≤5 clips, non-overlapping source ranges
- At least one clip tagged as headline in selection JSON
- Highlight `scores` must include `diversity_bonus` (schema-validated)

## Prompt / artifact QA

- After each LLM stage, `interview_mux.prompt_validation.validate_stage_artifacts` checks `artifacts` against `docs/cross-cutting/json-schemas/artifacts/*.schema.json`
- Failed validation triggers one automatic retry with error feedback in the message volley
- Golden fixtures: `tests/fixtures/prompts/` (optional regression snapshots)

**Operator workflow:** [operator-stage-checklists.md](../workflows/operator-stage-checklists.md) · **When something breaks:** [troubleshooting.md](../workflows/troubleshooting.md) · **Config caps / keys:** [config-keys.md](./config-keys.md)
