# comprehension-risk-blind examples (reference)

Specialist post-pass on `missing_framing` (and optionally `full_master_ranking`). Scores listener confusion per segment **without** rewriting gaps or proposing VO lines.

Pair with: `_shared/specialists/comprehension-risk-blind.system.txt` · [missing-framing.examples.md](../missing-framing.examples.md)

---

## Good — high risk with evidence

```json
{
  "status": "complete",
  "artifacts": {
    "comprehension_risks": [
      {
        "segment_id": "seg_042",
        "risk_score": 0.88,
        "rationale": "Answer discusses a 2024 pivot and 'the term sheet' with no prior mention of fundraising in adjacent segments."
      },
      {
        "segment_id": "seg_017",
        "risk_score": 0.72,
        "rationale": "Acronym 'SOC2 Type II' used for 90 seconds without expansion while guest assumes listener is a buyer."
      }
    ]
  },
  "confidence": 0.83,
  "reasoning_summary": "Two segments need framing attention; aligns with missing_framing gap_evaluations."
}
```

**Why:** `risk_score` 0–1; one-sentence rationale; real `segment_id` values only.

---

## Good — empty list when clear

```json
{
  "comprehension_risks": []
}
```

Valid when every segment is self-explanatory or `missing_framing` already marked low-severity bridges.

---

## Good — triggers investigation downstream

- `seg_042` `risk_score: 0.91` → parent stage enqueues `gap_unresolved` investigation.
- `missing_framing` re-run receives `comprehension_risks` in volley and prioritizes that segment.

---

## Good — technical_deep_dive calibration

- Jargon segment `risk_score: 0.65` (not 0.95) when interviewer briefly defines term in same segment.
- Rationale cites the defining sentence.

---

## Bad — proposes fixes

```json
{
  "segment_id": "seg_042",
  "risk_score": 0.9,
  "rationale": "Add VO: 'Earlier we discussed the Series B round…'"
}
```

**Why:** Specialist must not write VO or gap fixes — scoring only.

---

## Bad — risk without rationale

```json
{ "segment_id": "seg_010", "risk_score": 0.8 }
```

**Why:** Missing required `rationale` field.

---

## Bad — invent segment

- `segment_id: "seg_500"` not in manifest input.

**Why:** Score only segments present in input volley.

---

## Bad — uniform high scores

- All 45 segments `risk_score ≥ 0.85`.

**Why:** Degrades signal; parent `missing_framing` cannot prioritize; likely prompt drift.

---

## Bad — duplicates missing_framing verbatim

- Copies `listener_confusion` text from `gap_evaluations` without blind scoring.

**Why:** Specialist should independently assess risk; may score low when light bridge suffices.
