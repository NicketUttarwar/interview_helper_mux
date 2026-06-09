# Transcription

AWS Transcribe via CLI with speaker diarization.

**Source-of-truth catalogs (vendors, local OSS, policies):**

- [stt-and-diarization.md](./stt-and-diarization.md) — STT + diarization options (AWS implemented; alternatives for integration).
- [source-separation-and-enhancement.md](./source-separation-and-enhancement.md) — denoise / separation / enhancement before or after STT.

## Ticket

BUILD-021

## Tools

**AWS CLI** (`aws s3 cp`, `aws transcribe start-transcription-job`, poll `get-transcription-job`) — CLI pin: [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md#system-binaries). No boto3.

## Inputs

| Path | Description |
|------|-------------|
| `ingest/normalized.wav` | Uploaded to S3 (from [pre-clean](../audio_preclean/README.md) lineage when operator enabled full-source clean) |

## Outputs

| Path | Description |
|------|-------------|
| `transcript/full.json` | Words (with AWS `confidence`), segments, timestamps |
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

`AWS_S3_BUCKET`, `AWS_S3_INPUT_KEY`, `AWS_DEFAULT_REGION` in secrets

## Module

`src/interview_mux/stages/transcribe_aws.py`

## Prompts

None — see [docs/prompts/transcription/README.md](../../prompts/transcription/README.md)

---

## Build-out

BUILD-021, BUILD-018 (G0) · [README.md](../../build-out/README.md) · [repository-map.md](../../build-out/repository-map.md)
