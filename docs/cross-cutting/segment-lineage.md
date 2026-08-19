# Segment ID lineage

Canonical segment IDs (`seg_001`, `seg_002`, …) flow from **`segments/boundaries.json`** through **`segments/manifest.json`** into every analysis and delivery artifact that references speech spans.

`chapter_close_hitch` is the one allowed **full ID churn** after the first chapter map: it writes `mastering/chapter_close_hitch/remap.json` (`old_id → new_id` via overlap + `talking_point_id`) and rewrites surviving upstream refs (content brief, talking points, ideal cuts, operator must-keeps, NLE, **omit ledger**, **context index**, **gap report / VO filenames**). Unmatched must-keeps stay flagged, never silently dropped. Downstream of `boundary_detection` is archived on purpose so ranking / fuse / EDL cannot keep stale ids. A crash while the latch is `running` resumes without recutting again. After the inner restage, G1 `vo_pickup` WAVs and omit/skip rows are rebound onto the live ids, and `episode_structure` is aligned to the remapped chapters.

## Canonical sources

| Artifact | Role |
|----------|------|
| `segments/boundaries.json` | Timeline contract; IDs assigned by deterministic collate after `boundary_detection` (or republished by `chapter_close_hitch`) |
| `mastering/chapter_close_hitch/remap.json` | One-shot old→new `seg_*` table after the chapter-close recut |
| `segments/manifest.json` | Full segment rows (times, speaker, text, `topic_tags`) — runtime authority |
| `master/selection.json` | From `full_master_ranking` onward, delivery checks often use `ordered_segment_ids` |

## Artifacts that carry segment references

| Path | Key fields |
|------|------------|
| `understanding/content_brief.json` | `topics[].segment_ids`, `key_claims[].evidence_segment_ids`, `topic_relationships[].evidence_segment_ids` |
| `understanding/gap_evaluations.json` | `evaluations[].segment_id` |
| `understanding/gap_report.json` | `interviewer_lines[].targets_segment_id` |
| `understanding/episode_structure.json` | `segment_order[]`, `slot_plan[].bound_segment_ids`, `hook_reel.segment_id` |
| `master/coverage_audit.json` | `topic_mappings[].segment_ids`, `claim_mappings[].segment_ids`, `orphan_segment_ids` |
| `master/narrative_plan.json` | `chapters[].segment_ids`, `chapters[].suggested_open_segment_id`, `ordering_constraints[]` |
| `master/selection.json` | `ordered_segment_ids`, `excluded_segment_ids` |
| `master/transitions.json` | `before_segment_id`, `after_segment_id` |
| `master/edl.json` | `ordered_segment_ids`, speech/VO clip `segment_id` / `targets_segment_id` |

## Validation stack

1. **Write path** — `artifact_writes.write_validated_artifact()` normalizes boundaries/manifest, enforces `seg_NNN` format, syncs content brief after boundary commit.
2. **Repairs** — `artifact_repairs.py` drops orphan refs, infers narrative chapter `segment_ids`, rewrites NLE split parents to children. `chapter_close_hitch` uses map-replace (`apply_segment_id_map`), not orphan-drop.
3. **Cross-artifact checkpoints** — `artifact_cross_validate.py` at stage boundaries (`post_segmentation`, `post_reanchor`, `post_coverage_audit`, `post_episode_structure`, `post_edl`, …).
4. **Lineage audit** — `python tools/audit_segment_lineage.py --run-id <exec_id>` or `--fixture` (CI).

## Operator tools

```bash
# Full run audit
python tools/audit_segment_lineage.py --run-id exec_001_...

# CI fixture chain
python tools/audit_segment_lineage.py --fixture

# Contract + progression + lineage (CI)
./scripts/verify_artifact_contract.sh
```

The GUI Phase Workbench shows **segment lineage warnings** when orphan refs are detected on the active run.

## NLE splits

Timeline splits create synthetic IDs (`seg_001a`, `seg_001b`, … N-way via `cut_ms[]`). `propagate_nle_split_segment_refs()` rewrites upstream brief/coverage/narrative **and** selection / transitions / gap artifacts when a segment is split in the NLE editor.

Operator merge into selection uses **app auto order as base** with **operator-touched moves as overlays** (`apply_nle_to_selection`) — never dump untouched ids after a partial NLE sequence.

See also: [artifact-layout.md](./artifact-layout.md), [artifact-generation-and-validation.md](./artifact-generation-and-validation.md).
