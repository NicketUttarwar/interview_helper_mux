---
id: segmentation-silence
tier: both
status: spec
depends_on: [pipeline-segmentation]
---

# Silence and pause splits

Cheap, robust first pass: detect **gaps** in speech energy or long punctuation pauses in ASR text.

## Parameters

- Minimum silence duration (e.g. 400–800 ms).
- Maximum segment length (split long monologues).

## Open decisions

- Energy-based vs transcript-only when STT drops silent breaths.

## Links

- [topic-embedding-boundaries.md](topic-embedding-boundaries.md)
- [../scoring-and-selection/salience-heuristics.md](../scoring-and-selection/salience-heuristics.md)
