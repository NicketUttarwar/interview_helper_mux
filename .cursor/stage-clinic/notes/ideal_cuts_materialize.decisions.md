# Decisions — ideal_cuts_materialize

brain: 0.2.0

Append-only. Do not rewrite history.

| ts | layer | question | answer | implication |
|----|-------|----------|--------|-------------|
| 2026-09-17 | L1 | L1: align contract ideal_cuts soft→hard to match RuntimeError. | _(awaiting)_ | draft target backlog |
| 2026-09-17 | L3 | B1 contract ideal_cuts soft→hard? | Wave 2 yes | hard `understanding/ideal_cuts.json` (producer propose); propose mints path even when enable=false |
| 2026-09-17 | L3 | B2 soft-stale propose freshness gate? | Wave 2 skip — needs_you + FULL_AUTO_REGRESSION_RISK | open |
| 2026-09-18 | L3 | B2 soft-stale propose freshness? | **4A** leave soft | no freshness stall |
