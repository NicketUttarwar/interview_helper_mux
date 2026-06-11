# content-brief-reanchor examples (reference)

Pass-2 patch after `segment_classification`. Merges manifest `segment_ids` into topics, confirms/rejects hypotheses, and adds `topic_relationships` — without contradicting pass-1 `content_context`.

Pair with: `understanding/content-brief-reanchor.system.txt` · [content-context.examples.md](./content-context.examples.md)

---

## Good — topics grounded to manifest

```json
{
  "status": "complete",
  "artifacts": {
    "topics": [
      {
        "name": "Bootstrapped growth",
        "segment_ids": ["seg_004", "seg_011", "seg_019"],
        "confidence": 0.88,
        "summary": "Guest describes revenue-funded expansion without venture capital."
      },
      {
        "name": "Hiring first engineers",
        "segment_ids": ["seg_012", "seg_013"],
        "confidence": 0.82,
        "summary": "Founding team recruited from personal network in 2019."
      }
    ],
    "topic_relationships": [
      { "from": "Bootstrapped growth", "to": "Hiring first engineers", "relation": "enables" }
    ]
  },
  "memory_updates": {
    "themes_append": [
      { "segment_id": "seg_019", "topic_tags": ["bootstrapped_growth"] }
    ],
    "hypotheses_append": [
      { "hypothesis": "No institutional funding before 2022", "status": "confirmed", "evidence_segment_ids": ["seg_004", "seg_011"] }
    ]
  },
  "confidence": 0.86,
  "reasoning_summary": "All major topics mapped; hiring theme newly anchored from classification pass."
}
```

**Why:** Every topic has real `segment_ids`; relationships cite topic names from the same artifact; hypothesis status backed by evidence.

---

## Good — honest partial map with investigation

- Topic `"EU regulatory timeline"` has `segment_ids: []` after reanchor.
- `follow_up_investigations`: `{ "kind": "theme_unmapped", "question": "Brief mentions EU regulation but no segment supports it" }`.
- Thesis preserved from pass-1; confidence on that topic ≤ 0.4.

**Why:** Does not invent coverage; triggers downstream investigation instead of fake `segment_ids`.

---

## Good — style refine optional

- `memory_updates.style_patch.tone`: "Measured, founder-led — long answers, interviewer interrupts only for clarification"
- Only applied when classification revealed sustained monologue segments (`format_class: fireside`).

---

## Bad — orphan segment_ids

```json
{
  "topics": [
    { "name": "Product launch", "segment_ids": ["seg_099"], "confidence": 0.9 }
  ]
}
```

`seg_099` not in `segments/manifest.json` — fails `cross_artifact_refs_valid` lint and arbiter reject.

---

## Bad — contradicts pass-1 thesis

- Pass-1 thesis: "Guest bootstrapped without outside capital."
- Reanchor changes thesis to "Guest raised Series A in 2021" with only `seg_022` (a flagged G0 chunk, confidence 0.68).

**Why:** Contradicts grounded pass-1 without new clean evidence; ignores [transcript-quality-rubric.md](../transcript-quality-rubric.md).

---

## Bad — empty relationships when multiple topics

- Three topics with non-overlapping `segment_ids` but `topic_relationships: []` and no rationale.

**Why:** Arbiter reject — relationships required when ≥2 topics exist unless single-topic interview.

---

## Bad — copies generic themes without segment_ids

```json
{
  "name": "Innovation",
  "segment_ids": [],
  "summary": "The conversation touched on innovative thinking."
}
```

**Why:** Same failure as `content_context` generic-theme lint; reanchor must not leave pass-1 fluff ungrounded.

---

## Bad — full brief rewrite

- Output replaces entire `content_brief` structure instead of patch fields (`topics`, `topic_relationships`, `hypotheses`, targeted `confidence`).

**Why:** Stage contract is **reanchor**, not second full `content_context` pass.
