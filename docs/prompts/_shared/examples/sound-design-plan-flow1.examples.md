# sound-design-plan-flow1 examples (reference)

Flow 1 SDP patch: `assets[]` + `flow_plans.flow1.cues[]` aligned to `full_master_ranking` and palettes.

Pair with: `sound_design/plan-flow1.system.txt` · [post-generation-placement.md](../../../cross-cutting/post-generation-placement.md)

---

## Good — asset reuse + bed cues

```json
{
  "status": "complete",
  "artifacts": {
    "assets": [
      {
        "asset_id": "chapter_stinger_warm",
        "role": "chapter_stinger",
        "duration_seconds": 1.6,
        "palette_id": "farm_morning_exterior"
      },
      {
        "asset_id": "ambient_farm_morning",
        "role": "ambient_bed",
        "duration_seconds": 8.0,
        "palette_id": "farm_morning_exterior"
      }
    ],
    "flow_plans": {
      "flow1": {
        "cues": [
          {
            "cue_id": "bed_seg_018",
            "asset_id": "ambient_farm_morning",
            "placement": "under_segment",
            "segment_id": "seg_018",
            "level_db": -26,
            "duck_under_speech_db": 18
          },
          {
            "cue_id": "stinger_ch02",
            "asset_id": "chapter_stinger_warm",
            "placement": "after_segment",
            "after_segment_id": "seg_025",
            "level_db": -14
          }
        ]
      }
    }
  },
  "confidence": 0.87,
  "reasoning_summary": "Two assets serve full master; stinger reused at chapter ends from narrative_plan."
}
```

**Why:** ≤6 assets; bed only on palette-mapped segments; stinger at chapter boundary; duck explicit.

---

## Good — mix contract hints embedded

```json
{
  "placement_hints": {
    "stinger_min_pause_after_speech_ms": 400,
    "prefer_stinger_after_pause_tail": true
  },
  "stinger_max_per_minute": 2
}
```

Passed to SAP / mix engine via `source_acoustic_profile` merge.

---

## Good — VO bridge cue placeholder

```json
{
  "cue_id": "bridge_seg_042",
  "asset_id": "vo_bridge_texture",
  "role": "vo_bridge",
  "placement": "before_segment",
  "segment_id": "seg_042",
  "level_db": -18,
  "note": "Duration finalized by sound_design_vo_finalize after G1 pickup"
}
```

---

## Bad — bed on segment outside palette

- `ambient_farm_morning` palette maps `seg_018`–`seg_022` only.
- Cue `under_segment` on `seg_040`.

**Why:** `sdp_cross_validate` + deterministic lint reject.

---

## Bad — six unique chapter stingers

```json
{
  "assets": [
    { "asset_id": "stinger_ch01", "role": "chapter_stinger" },
    { "asset_id": "stinger_ch02", "role": "chapter_stinger" },
    { "asset_id": "stinger_ch03", "role": "chapter_stinger" },
    { "asset_id": "stinger_ch04", "role": "chapter_stinger" },
    { "asset_id": "stinger_ch05", "role": "chapter_stinger" },
    { "asset_id": "stinger_ch06", "role": "chapter_stinger" }
  ]
}
```

**Why:** Exceeds reuse pattern; timbral drift; may hit `max_assets_flow1` cap.

---

## Bad — cue anchor not in selection

- `segment_id: "seg_099"` in cue but absent from `flow_1_master/selection.json` `ordered_segment_ids`.

**Why:** Lint `cue anchor not in selection`.

---

## Bad — stinger over dense jargon chain

- `after_segment` stinger on `seg_015` where SAP shows `pause_p50_ms: 120` and no pause ≥400 ms in transcript.

**Why:** Mix will miss pause alignment; choose `before_segment` on next moderator question instead.

---

## Bad — contradictory sonic_identity

- Palettes `coherence.sonic_identity`: "Cold institutional minimalism"
- Plan adds warm farm beds on every segment without narrative reason.

**Why:** Arbiter reject — plan must align with upstream palettes coherence block.
