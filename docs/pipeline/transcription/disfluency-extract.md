# Disfluency extract (G0.5)

After **transcript review (G0)**, `disfluency_extract` scans inter-word gaps in the AWS transcript using energy-based VAD and optional local **faster-whisper** on gap clips. Events matching the filler lexicon (`um`, `uh`, `er`, …) are written to `transcript/disfluencies.json` with pre-cut WAV clips under `transcript/disfluency_clips/`.

## Gate

**disfluency_review** is a blocking gate when extract is enabled and events exist. Operators confirm or reject each event in the GUI before `source_acoustic_profile` and downstream analysis run.

When `disfluency_extract.enabled` is false, the stage no-ops, writes a skipped artifact, and auto-marks both extract and review done.

## Artifacts

| Path | Role |
|------|------|
| `transcript/disfluencies.json` | Event catalog + review status |
| `transcript/disfluency_clips/*.wav` | Per-event audio clips |
| `transcript/disfluency_review.json` | Operator sign-off summary |

## Config

See `disfluency_extract.*` in `config/app.defaults.json`. Prefetch Whisper weights with `python scripts/download_local_stt.py`.

## LLM context

After G0.5 review completes, downstream analysis stages receive optional `disfluency_catalog` in stage input (confirmed filler events, per-segment counts). See [analysis-preamble.system.txt](docs/prompts/_shared/analysis-preamble.system.txt).

## Restore phase

Confirmed fillers can be spliced back into Flow 1 assembly — see [disfluency-restore.md](../assembly_and_mux/disfluency-restore.md).
