---
id: audio-cut-boundaries
tier: both
status: spec
depends_on: [pipeline-audio-editing]
---

# Cut boundaries (samples)

Cuts should land on **zero crossings** or short pre-roll when possible to avoid clicks; word timestamps give **approximate** sample ranges—refine with local search or constrained snap.

## Open decisions

- Fixed pre-roll/post-roll padding (e.g. 100–300 ms) vs dynamic per phoneme.

## Links

- [crossfades-room-tone.md](crossfades-room-tone.md)
- [../snippet-store/segment-manifest-and-storage.md](../snippet-store/segment-manifest-and-storage.md)
