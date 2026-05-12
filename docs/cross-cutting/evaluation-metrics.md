---
id: cross-eval-metrics
tier: both
status: spec
depends_on: []
---

# Evaluation metrics

Personal-use does not mean **no quality bar**: pick a small set of metrics to compare tiers and config changes.

## Transcript quality

- **WER/CER** if you have reference text (rare); otherwise subjective rubric per episode.
- **Confidence histogram** from STT; low tail correlates with bad cuts.

## Segmentation / selection

- **Boundary plausibility:** manual spot-check count per hour.
- **Redundancy rate:** average pairwise embedding similarity among selected segments (lower can be better).

## Listening

- **Loudness compliance:** integrated LUFS and true peak on final master.
- **Clip click count** on boundaries after automated assembly.

## Open decisions

- Minimum listening checklist before declaring a master “done.”

## Links

- [../versions/capability-matrix.md](../versions/capability-matrix.md)
- [../execution/complexity-ladder-end-to-end-ideas.md](../execution/complexity-ladder-end-to-end-ideas.md)
- [../workflows/parallel-segmentation-candidates.md](../workflows/parallel-segmentation-candidates.md)
