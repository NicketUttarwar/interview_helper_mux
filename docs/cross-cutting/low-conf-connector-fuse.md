# Low-confidence islands + connector seam fuse

Doctrine for **recall-first** low-confidence clustering, **economy-LLM seam adjudication**,
density top-decile hard must-keep, and how those layers feed selection + Nugget Layup.

Related: [nugget-layup-system.md](./nugget-layup-system.md) · [mastering-process.md](./mastering-process.md) · [config-keys.md](./config-keys.md)

## Why

After STT + boundary cuts, two failure modes hurt the master:

1. **Lexicon / code-switch islands** — low-confidence stretches interleaved with confident English (lingua franca). Soft prefer-include alone is not a membership guarantee.
2. **Poor connector cuts** — segment A ends mid-thought; chronological B continues. The master airs a chop then a restart.

## Pipeline placement

```text
vernacular_segment_sanitize
  → low_conf_island_scan          # ladder + density + top 10% must_keep
  → connector_fuse_pass           # post_sanitize seam LLM loop
  → … Shape / gaps …
  → connector_fuse_pass_pre_ranking
  → full_master_ranking           # pack cannot drop low-conf must_keep
  → nugget_corpus_mine / layup    # five-layer VO with degraded path
```

Junction QA may schedule `pass_id=junction_heal` when incomplete residuals remain between selected natives.

## Cluster ladder (recall-first)

| Tier | `cluster_kind` | Rule |
|------|----------------|------|
| 1 | `tight` | Consecutive low-confidence words |
| 2 | `loose` | Sliding window tolerates high-conf English sprinkle when `low_ratio` holds |
| 3 | `window` | Fixed ms windows with low mean conf or brick count |
| 4 | `segment_soft` | Whole-segment soft density (reduced weight) |

English high-conf tokens **inside** a candidate do **not** end the cluster. Noise demotion is **narrow** (unpadded + zero lexicon signal only).

Artifacts: `analysis/low_conf_islands.json`, `analysis/low_conf_density_ranking.json`, `analysis/low_conf_must_keep.json`.

## Seam LLM loop

Deterministic code enumerates **every** chronological adjacent pair (`tail_words` + `head_words` → packet). The economy stage `connector_seam_adjudicate` decides `fuse` vs `stay_independent`. Code applies fuses by rewriting `segments/manifest.json` + `segments/boundaries.json` into **one** complete-thought segment (`fused_from`).

```text
loop until applied == 0 (fixed point) or identical fuse signature (oscillation halt)
  packets = enumerate all adjacent pairs
  verdicts = LLM (economy → standard → flagship; halve batch on context_length)
  apply fuses (no count budget; editorial seam-safety still applies)
re-run resolve_keeper_air_bounds on fused slabs
junction_heal uses force_readjudicate=True
```

Artifacts: `analysis/connector_seam_packets.json`, `analysis/connector_seam_verdicts.json`, `analysis/connector_fuse_audit.json`, `analysis/connector_fuse_rounds.json`.

Cross-speaker fuse is off by default. Island-straddle cuts force fuse even if the LLM preferred stay.

## Selection guarantee

Top `analysis.low_conf_selection.top_percentile` (default **10%**) of **positive-density** natives become hard must_keep via `authoritative_must_keep_ids`. Non-decile positives keep soft prefer-include boosts.

## Modules

- `src/interview_mux/low_conf_islands.py`
- `src/interview_mux/segment_fuse.py`
- `src/interview_mux/stages/low_conf_fuse_stages.py`
