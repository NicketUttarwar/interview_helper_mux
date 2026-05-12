---
id: ingest-normalization
tier: both
status: spec
depends_on: [pipeline-ingest]
---

# Normalization and format

Standardize audio so STT and ffmpeg pipelines see **consistent** input.

## Typical targets

- **Sample rate:** 16 kHz mono for many STT APIs; 48 kHz if you keep high-quality intermediate for editing.
- **Channels:** downmix to mono for STT; retain multichannel only if diarization benefits.
- **True peak / LUFS:** light gain staging before STT; aggressive mastering deferred to [../mastering-and-export/final-loudness-limiting.md](../mastering-and-export/final-loudness-limiting.md).

## Open decisions

- Single “canonical” intermediate format (e.g. WAV PCM vs FLAC).

## Links

- [chunking-long-interviews.md](chunking-long-interviews.md)
- [../transcription/stt-provider-adapters.md](../transcription/stt-provider-adapters.md)
