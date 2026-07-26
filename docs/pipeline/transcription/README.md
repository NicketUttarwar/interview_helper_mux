# Transcription

Local MLX STT (mlx-audio) with speaker diarization. No cloud STT.

**Source-of-truth catalogs (vendors, local OSS, policies):**

- [stt-and-diarization.md](./stt-and-diarization.md) — STT + diarization options (local MLX implemented; alternatives for integration).
- [source-separation-and-enhancement.md](./source-separation-and-enhancement.md) — denoise / separation / enhancement before or after STT.

## Ticket

BUILD-021

## Tools

**Local MLX runtime** in `ASSETS/local_speech/venv` via `tools/stt_transcribe.py`. Bootstrap with `./scripts/bootstrap_venv.sh`; verify with `./scripts/verify_local_models.sh`.

## Inputs

| Path | Description |
|------|-------------|
| `ingest/normalized.wav` | Transcribed in place (from [pre-clean](../audio_preclean/README.md) lineage when operator enabled full-source clean) |

## Outputs

| Path | Description |
|------|-------------|
| `transcript/full.json` | Words (with per-word `confidence`), segments, timestamps |
| `transcript/speakers.json` | Speaker label summary |
| `transcript/review_queue.json` | Ranked STT review chunks (after prep) |
| `transcript/review_clips/*.wav` | Pre-cut audio per review chunk |
| `transcript/corrections.json` | Operator text fixes |

## Transcript review (G0)

After transcription, operators correct STT in the GUI before analysis continues:

- **Synced transcript dock** — word-level karaoke editor with immediate `PATCH …/transcript/words` saves
- **Fuzzy similar-word replace** — batch-fix repeated mishearings across the full transcript (client-side matcher, 80–100% strictness)

See [transcript-review.md](./transcript-review.md).

## Config

No secrets required — the model runs locally. Model choice comes from `local_speech.*` in `config/app.defaults.json`.

## Module

`src/interview_mux/stages/transcribe_local.py`

## Prompts

None — see [docs/prompts/transcription/README.md](../../prompts/transcription/README.md)

---

