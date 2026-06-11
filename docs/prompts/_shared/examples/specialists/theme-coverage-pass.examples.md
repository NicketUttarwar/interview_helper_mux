# theme-coverage-pass examples (reference)

Specialist post-pass on `segment_classification`. Patches `topic_tags` on segments where brief themes lacked manifest coverage after primary classification.

Pair with: `_shared/specialists/theme-coverage-pass.system.txt` · [segment-classification.examples.md](../segment-classification.examples.md)

---

## Good — confident patch from brief vocabulary

```json
{
  "status": "complete",
  "artifacts": {
    "segment_topic_patches": [
      {
        "segment_id": "seg_031",
        "topic_tags": ["supply_chain_resilience"]
      },
      {
        "segment_id": "seg_032",
        "topic_tags": ["supply_chain_resilience", "inventory_automation"]
      }
    ]
  },
  "confidence": 0.79,
  "reasoning_summary": "Guest discusses warehouse automation and buffer stock — maps to brief topic 'Supply chain resilience'."
}
```

**Why:** Tags use brief/snake_case vocabulary; 1–3 tags per segment; patches only unmapped segments.

---

## Good — empty when nothing confident

```json
{
  "segment_topic_patches": []
}
```

Valid when primary `segment_classification` already mapped all brief topics.

---

## Good — triggers theme_unmapped resolution

- Before patch: brief topic `"Open source strategy"` had zero `segment_ids`.
- After patch applied to `seg_044`, `seg_045`: investigation cleared; `content_brief_reanchor` can re-run with lower priority.

---

## Good — panel segment single-speaker tag

- `seg_028` is one panelist's answer about regulation.
- `topic_tags: ["eu_regulation"]` only — does not tag other panelists' themes on same segment.

---

## Bad — invents new theme name

```json
{
  "segment_id": "seg_010",
  "topic_tags": ["cool_innovation_stuff"]
}
```

**Why:** Not in `content_brief.topics`; specialist must use existing brief names/tags.

---

## Bad — patches already-mapped segment

- `seg_004` already has `topic_tags: ["bootstrapped_growth"]` in manifest.
- Patch replaces with unrelated tags without `theme_unmapped` trigger.

**Why:** Patch only **unmapped** gaps; do not churn good classification.

---

## Bad — too many tags

```json
{
  "topic_tags": ["a", "b", "c", "d", "e"]
}
```

**Why:** Max 1–3 tags per rules; dilutes palette mapping.

---

## Bad — rewrites content brief

- Output includes `topics[]` or `thesis` changes.

**Why:** Artifact shape is `segment_topic_patches` only.

---

## Bad — tags from flagged G0 chunk only

- `seg_022` text entirely inside `transcript_quality.flagged_chunks` (conf 0.69).
- High-confidence patch on precise funding claim.

**Why:** Lower confidence or skip patch until G0 clears — [transcript-quality-rubric.md](../../transcript-quality-rubric.md).
