# Segment ID lineage

Canonical segment IDs (`seg_001`, `seg_002`, …) flow from **`segments/boundaries.json`** through **`segments/manifest.json`** into every analysis and delivery artifact that references speech spans.

## Canonical sources

| Artifact | Role |
|----------|------|
| `segments/boundaries.json` | Timeline contract; IDs assigned by deterministic collate after `boundary_detection` |
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
2. **Repairs** — `artifact_repairs.py` drops orphan refs, infers narrative chapter `segment_ids`, rewrites NLE split parents to children.
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

Timeline splits create synthetic IDs (`seg_001a`, `seg_001b`). `propagate_nle_split_segment_refs()` rewrites upstream brief/coverage/narrative references when a segment is split in the NLE editor.

See also: [artifact-layout.md](./artifact-layout.md), [artifact-generation-and-validation.md](./artifact-generation-and-validation.md).
