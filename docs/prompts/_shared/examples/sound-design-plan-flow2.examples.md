# sound-design-plan-flow2 examples (reference)

Flow 2 SDP patch: montage `assets[]` + `flow_plans.flow2.cues[]` for highlight reel transitions and cold open.

Pair with: `sound_design/plan-flow2.system.txt` · [sound-design.examples.md](./sound-design.examples.md)

---

## Good — single shared transition asset

```json
{
  "status": "complete",
  "artifacts": {
    "assets": [
      {
        "asset_id": "montage_whoosh_soft",
        "role": "transition_stinger",
        "duration_seconds": 1.2,
        "reuse_note": "All between_clips cues"
      },
      {
        "asset_id": "cold_open_pulse",
        "role": "cold_open",
        "duration_seconds": 2.0
      }
    ],
    "flow_plans": {
      "flow2": {
        "cues": [
          {
            "cue_id": "open_01",
            "asset_id": "cold_open_pulse",
            "placement": "cold_open",
            "level_db": -8
          },
          {
            "cue_id": "cut_1_2",
            "asset_id": "montage_whoosh_soft",
            "placement": "between_clips",
            "from_clip_rank": 1,
            "to_clip_rank": 2,
            "level_db": -11
          },
          {
            "cue_id": "cut_2_3",
            "asset_id": "montage_whoosh_soft",
            "placement": "between_clips",
            "from_clip_rank": 2,
            "to_clip_rank": 3,
            "level_db": -12
          }
        ]
      }
    }
  },
  "confidence": 0.85,
  "reasoning_summary": "Two assets; one transition timbre across montage; levels vary per cut energy."
}
```

**Why:** ≤4 assets; shared `transition_stinger`; ranks match `highlight_selection` clips.

---

## Good — cold open overlap intent

- `cold_open` cue notes: "Overlap first 200 ms of rank-1 clip at −12 dB — mix applies layer stack"
- Matches [post-generation-placement.md](../../../cross-cutting/post-generation-placement.md) Flow 2 pattern.

---

## Good — sparse SFX on debate format

- Only `between_clips` cues; no `cold_open` when `format_class: debate` (energy already high).
- `stinger_max_per_minute: 4` unchanged but only 3 cuts → 2 transitions.

---

## Bad — per-cut unique assets

```json
{
  "cues": [
    { "cue_id": "cut_1_2", "asset_id": "whoosh_a", "placement": "between_clips" },
    { "cue_id": "cut_2_3", "asset_id": "whoosh_b", "placement": "between_clips" },
    { "cue_id": "cut_3_4", "asset_id": "whoosh_c", "placement": "between_clips" }
  ]
}
```

**Why:** Montage cohesion break; extra API spend; v1 anti-pattern.

---

## Bad — invalid clip ranks

- `from_clip_rank: 5` when `flow_2_highlights/selection.json` has ranks 1–4 only.

**Why:** Lint `cue rank not in highlight selection`.

---

## Bad — bed under montage clip

- `placement: under_segment` on highlight clip rank 2 in Flow 2 plan.

**Why:** Flow 2 montage is speech-forward cuts; beds belong in Flow 1 full master, not highlight reel.

---

## Bad — cold open on trauma peak

- Rank-1 clip is isolated grief disclosure without surrounding context.
- Plan still adds triumphant `cold_open_pulse` at −8 dB.

**Why:** [interview-scenario-atlas.md](../interview-scenario-atlas.md) `trauma_adjacent` — no cold open on disclosure peak.

---

## Bad — transition level too hot

- All `between_clips` cues at `level_db: -6` on already energetic clips.

**Why:** Post-listen fail predictable; speech masked; default montage transitions −10 to −14 dB.
