---
id: audio-loudness-working
tier: both
status: spec
depends_on: [pipeline-audio-editing]
---

# Loudness targets (working)

Separate **working loudness** for editing from **delivery loudness** for podcast platforms.

## Guidance

- Normalize per-clip to similar **integrated LUFS** before mux so level rides are minimal.
- Avoid brick-wall limiting until [../mastering-and-export/final-loudness-limiting.md](../mastering-and-export/final-loudness-limiting.md).

## Open decisions

- Target working LUFS for speech (e.g. -18 vs -24 LUFS for headroom).

## Links

- [../mastering-and-export/final-loudness-limiting.md](../mastering-and-export/final-loudness-limiting.md)
