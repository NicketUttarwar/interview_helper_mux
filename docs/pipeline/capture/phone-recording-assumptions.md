---
id: capture-phone-assumptions
tier: both
status: spec
depends_on: [pipeline-capture]
---

# Phone recording assumptions

Single **continuous** recording per session; downstream treats it as **one master timeline** (with optional chapter markers added later, not multiple independent files).

## Assumptions to fix in your setup

- **Container:** WAV, M4A, AAC in MP4, etc.—ingest must know codecs.
- **Channels:** mono is simplest for STT; stereo may carry spatial cues but complicates diarization if split L/R incorrectly.
- **Sample rate:** 44.1 kHz vs 48 kHz phone defaults; ingest normalizes.
- **Session length:** hours-long files imply **chunked STT** or streaming upload strategies.

## Open decisions

- Whether to record lossless where the phone allows it.

## Links

- [../ingest/chunking-long-interviews.md](../ingest/chunking-long-interviews.md)
- [clipping-and-headroom.md](clipping-and-headroom.md)
