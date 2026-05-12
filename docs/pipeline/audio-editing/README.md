---
id: pipeline-audio-editing
tier: both
status: spec
depends_on: [pipeline-snippet-store]
---

# Audio editing

Turn selected time ranges into **clean clips**: boundary choices, fades, room tone, working loudness.

## In this folder

| Topic | File |
|-------|------|
| Sample boundaries | [cut-boundaries-samples.md](cut-boundaries-samples.md) |
| Transitions | [crossfades-room-tone.md](crossfades-room-tone.md) |
| Working LUFS | [loudness-targets-lufs.md](loudness-targets-lufs.md) |

## Next stage

[../assembly-and-mux/README.md](../assembly-and-mux/README.md)

## Open decisions

- Whether to denoise before or after segmentation scoring.

## Links

- [../transcription/word-level-timestamps.md](../transcription/word-level-timestamps.md)
