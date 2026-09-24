# Fixture: exec_13183 Cluster D / i9 (EDL survivors after orientation)

Extracted from live run `exec_13183_d19c15b58ab4_20260924T001619Z` (Mohan full-auto).

## What failed in the real run

1. `pre_mix` publishability: `vo_audibility_drift` — WAV on disk for
   `vo_layup_seg_007` / `vo_layup_seg_037` but no EDL `vo_pickup` seat
   (after opening orientation VO stacked and wiped later before-lines).
2. Heal rebuild blocked: `edl_unsanitary: master/assembly_ledger.json missing`.

## Files

| File | Role |
|------|------|
| `gap_report.json` | Live gap (orientation + 2 nugget_layup lines) |
| `selection.json` | Ordered keep list (35 segs) |
| `segments_manifest.json` | Slimmed `segments/manifest.json` for those keeps |
| `edl_seated.json` | Post-fix ship EDL (all 3 VO seats present) |
| `edl_wiped_phantoms.json` | Same EDL with layup seats stripped (bug reconstitution) |
| `forensics_excerpt.json` | Real fingerprint strings from operator forensics |

WAVs are **not** committed (large). Tests copy them from
`ASSETS/executions/exec_13183_…/vo_pickup/synthesized/` when present, else
mint short stand-in WAVs with the same line_id filenames so seating still runs.
