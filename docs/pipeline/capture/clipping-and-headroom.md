---
id: capture-clipping-headroom
tier: both
status: idea
depends_on: [pipeline-capture]
---

# Clipping and headroom

Distorted peaks **cannot** be recovered; STT and separation models degrade on clipped speech.

## Capture-side guidance

- Leave **headroom**; avoid “brick wall” auto gain that pumps noise.
- If clipping is visible in waveform analysis at ingest, **flag** the session for manual listen.

## Open decisions

- Optional real-time level meter app vs post-hoc analysis only.

## Links

- [../ingest/normalization-and-format.md](../ingest/normalization-and-format.md)
- [../audio-editing/loudness-targets-lufs.md](../audio-editing/loudness-targets-lufs.md)
