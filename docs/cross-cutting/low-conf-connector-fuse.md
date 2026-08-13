# Low-confidence islands + connector seam fuse

Doctrine for **recall-first** low-confidence clustering, **high-value speech islands**
(volume-gated STT-skip / multi low-conf), **economy-LLM seam adjudication**,
density top-decile + high-value hard must-keep, and how those layers feed selection + Nugget Layup.

Related: [nugget-layup-system.md](./nugget-layup-system.md) · [mastering-process.md](./mastering-process.md) · [config-keys.md](./config-keys.md)

## Why

After STT + boundary cuts, three failure modes hurt the master:

1. **Lexicon / code-switch islands** — low-confidence stretches interleaved with confident English (lingua franca). Soft prefer-include alone is not a membership guarantee.
2. **STT-skip speech** — other-language / domain / passionate bursts where Whisper emits **no words** for multi-second speech energy. Classic ladders never see these.
3. **Poor connector cuts** — segment A ends mid-thought; chronological B continues. The master airs a chop then a restart.

## Pipeline placement

```text
vernacular_segment_sanitize
  → low_conf_island_scan          # ladder + density + top 10% must_keep
                                  # + high_value_speech_islands (volume gate)
  → connector_fuse_pass           # per-cluster HV fuse (economy structure for multi)
                                  #   then global seam LLM on unlocked pairs
  → … Shape / gaps …
  → connector_fuse_pass_pre_ranking
  → full_master_ranking           # pack cannot drop low-conf / high-value must_keep
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

## High-value speech islands (volume-gated)

Detect **0+** islands where speech is present but STT is sparse or low-conf:

| Kind | Signal | Gate |
|------|--------|------|
| `stt_skip_energy` | Word-timeline gap ≥ `min_gap_ms` (default 2s) with speech-like RMS | Level within `level_ratio_min..max` of tape median RMS |
| `low_conf_cluster` | Existing non-noise tight/loose/window with ≥3 words **or** ≥1.5s | Same volume gate |

Single low bricks and quiet gaps are **rejected**. Passionate / other-language / domain bursts with near-average volume qualify.

**Never standalone keepers.** Flow-preserving **island clusters** then absorb them:

1. `group_high_value_island_clusters` joins same-flow L islands (`H–L–H–L–H`); separates on long H break or (one H + topic/subtopic change). Hinge H gets `hinge_attach=left|right`.
2. **simple** (one L): deterministic left/right/bridge via richer-neighbor.
3. **multi** (2+ L): one economy call per cluster — `island_cluster_structure_adjudicate` (structure only; richest local packet).
4. Exact cuts from **high-confidence flanks**; forced fuses lock seams so the global seam LLM cannot undo them.
5. Loop until no fuse-eligible clusters remain.

Artifacts: `analysis/high_value_speech_islands.json`, `analysis/high_value_speech_boosts.json`, `analysis/high_value_island_clusters.json`, `analysis/island_cluster_structure_packets.json`, `analysis/island_cluster_structure_verdicts.json`, `analysis/connector_fuse_locked_seams.json`.

Config: `analysis.high_value_speech_islands.*` — see [config-keys.md](./config-keys.md).

On **`connector_fuse_pass_pre_ranking`**, cluster separation also consults narrative arc / plan chapters when present (`narrative_chapter_change`).

## Seam LLM loop

Deterministic code enumerates **every** chronological adjacent pair (`tail_words` + `head_words` → packet). The economy stage `connector_seam_adjudicate` decides `fuse` vs `stay_independent`. Locked seams from HV cluster cuts stay independent. Code applies fuses by rewriting `segments/manifest.json` + `segments/boundaries.json` into **one** complete-thought segment (`fused_from`).

```text
per-cluster HV fuse rounds (structure LLM for multi; H-edge cuts; lock seams)
loop until applied == 0 (fixed point) or identical fuse signature (oscillation halt)
  packets = enumerate all adjacent pairs (skip / force-keep locked)
  verdicts = LLM (economy → standard → flagship; halve batch on context_length)
  apply fuses (no count budget; editorial seam-safety still applies)
re-run resolve_keeper_air_bounds on fused slabs
junction_heal uses force_readjudicate=True
```

Artifacts: `analysis/connector_seam_packets.json`, `analysis/connector_seam_verdicts.json`, `analysis/connector_fuse_audit.json`, `analysis/connector_fuse_rounds.json`.

Cross-speaker fuse is off by default. Island-straddle and high-value force fuse even if the LLM preferred stay.

## Selection guarantee

- Top `analysis.low_conf_selection.top_percentile` (default **10%**) of **positive-density** natives become hard must_keep.
- **Union** every segment touching a high-value island (post-fuse remapped IDs).
- Non-decile positives keep soft prefer-include boosts; high-value boosts use `importance_score` ≥ pack protect threshold so creative_pack cannot drop them.

## Modules

- `src/interview_mux/low_conf_islands.py`
- `src/interview_mux/high_value_speech_islands.py` (`group_high_value_island_clusters`)
- `src/interview_mux/island_cluster_structure.py`
- `src/interview_mux/segment_fuse.py` (`run_high_value_cluster_fuse_rounds`, `plan_cluster_fuses`)
- `src/interview_mux/stages/low_conf_fuse_stages.py`
