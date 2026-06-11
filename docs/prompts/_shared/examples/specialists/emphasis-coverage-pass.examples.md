# emphasis-coverage-pass examples (reference)

Specialist post-pass on `topic_coverage_audit`. Maps acoustic emphasis regions (from `stage_enrichment.emphasis_regions`) to narrative beats in the content brief.

Pair with: `_shared/specialists/emphasis-coverage-pass.system.txt` · [topic-coverage-audit.examples.md](../topic-coverage-audit.examples.md)

---

## Good — matched beat with segment anchor

```json
{
  "status": "complete",
  "artifacts": {
    "emphasis_coverage": {
      "matched_beats": [
        {
          "segment_id": "seg_018",
          "beat": "ICP pivot after enterprise pilots"
        },
        {
          "segment_id": "seg_024",
          "beat": "First profitable quarter"
        }
      ],
      "gaps": []
    }
  },
  "confidence": 0.81,
  "reasoning_summary": "High-emphasis regions align with brief key_claims and narrative_plan beats."
}
```

**Why:** `beat` labels come from brief/narrative vocabulary; `segment_id` from input emphasis regions.

---

## Good — gap reported honestly

```json
{
  "emphasis_coverage": {
    "matched_beats": [
      { "segment_id": "seg_012", "beat": "Founding story" }
    ],
    "gaps": [
      {
        "segment_id": "seg_033",
        "reason": "Guest voice rises on 'we almost shut down' but no brief beat or claim covers near-collapse narrative."
      }
    ]
  }
}
```

**Why:** Gap triggers `emphasis_coverage.gaps` investigation → optional coverage re-audit or `narrative_arc_plan` update.

---

## Good — empty arrays when flat delivery

```json
{
  "emphasis_coverage": {
    "matched_beats": [],
    "gaps": []
  }
}
```

Valid for monotone technical readout with no acoustic emphasis spikes in input.

---

## Good — does not change rankings

- Output contains only `emphasis_coverage` — no `ordered_segment_ids`, no `coverage_score` override.

---

## Bad — changes coverage audit scores

```json
{
  "emphasis_coverage": { "gaps": [] },
  "coverage_score": 1.0
}
```

**Why:** Specialist must not emit parent-stage fields; audit shape only.

---

## Bad — gap without reason

```json
{
  "gaps": [{ "segment_id": "seg_033" }]
}
```

**Why:** `reason` required — one evidence-based sentence.

---

## Bad — beat label invented

```json
{
  "beat": "The big moment"
}
```

**Why:** Use brief topic names, `key_claims` text, or `narrative_plan` chapter titles.

---

## Bad — segment not in emphasis input

- Reports `seg_050` but `emphasis_regions` volley listed only `seg_012`–`seg_040`.

**Why:** Use real `segment_id` values from specialist input only.

---

## Bad — treats volume spike as emphasis without transcript support

- Gap on `seg_022` citing "loudness" when segment is noisy-room STT artifact, not editorial emphasis.

**Why:** Cross-check with transcript content and [transcript-quality-rubric.md](../../transcript-quality-rubric.md); noisy_room may produce false emphasis.
