# Transcription

AWS Transcribe via CLI with speaker diarization.

## Ticket

BUILD-021

## Tools

`aws s3 cp`, `aws transcribe start-transcription-job`, poll `get-transcription-job`

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

After transcription, operators correct STT in the GUI before analysis continues. See [transcript-review.md](./transcript-review.md).

## Config

`AWS_S3_BUCKET`, `AWS_S3_INPUT_KEY`, `AWS_DEFAULT_REGION` in secrets

## Module

`src/interview_mux/stages/transcribe_aws.py`

## Prompts

None — see [docs/prompts/transcription/README.md](../../prompts/transcription/README.md)
