---
id: transcription-diarization
tier: high
status: idea
depends_on: [pipeline-transcription]
---

# Diarization

Label **speaker turns** (Speaker A / B or anonymous `spk_0`) to improve segmentation and final podcast clarity.

## Modes

- **Bundled** with STT provider.
- **Separate model** (embedding + clustering) for high-risk tier.

## Pitfalls

- Overlapping speech; short backchannels; similar voices.

## Open decisions

- Map diarization labels to roles (“you” vs “guest”) manually or heuristically.

## Links

- [../segmentation/topic-embedding-boundaries.md](../segmentation/topic-embedding-boundaries.md)
- [../human-review-ui/force-include-exclude.md](../human-review-ui/force-include-exclude.md)
