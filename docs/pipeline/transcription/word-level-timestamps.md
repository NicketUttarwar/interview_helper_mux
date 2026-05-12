---
id: transcription-word-timestamps
tier: both
status: spec
depends_on: [pipeline-transcription]
---

# Word-level timestamps

Segment scoring and **sample-accurate cuts** need alignments finer than paragraph breaks.

## Requirements

- Prefer **start/end per token** or per word from the STT API.
- If only segment-level times exist, run **forced alignment** (separate tool) as a high-risk option.

## Open decisions

- Minimum resolution acceptable for auto-cuts (word vs phrase).

## Links

- [../snippet-store/segment-manifest-and-storage.md](../snippet-store/segment-manifest-and-storage.md)
- [../audio-editing/cut-boundaries-samples.md](../audio-editing/cut-boundaries-samples.md)
