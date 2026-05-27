# Evaluation metrics

**Measurement tools:** `ffprobe` / `ffmpeg` now; `pyloudnorm` (BUILD-070) — pins in [anchored-toolchain.md](./anchored-toolchain.md).

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

**v1:** Tool runs `ffprobe` only (format/duration). **Target (BUILD-070):** measure LUFS and true peak; fail with actionable message in GUI.

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
