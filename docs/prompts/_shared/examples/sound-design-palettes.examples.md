# sound-design-palettes examples (reference)

Theme-to-sonic mapping before flow plans. Output patches `understanding/sound_design_plan.json` with `palettes[]` and `coherence` block.

Pair with: `sound_design/theme-palettes.system.txt` · [sound-design.examples.md](./sound-design.examples.md)

---

## Good — palette grounded in segment tags

```json
{
  "status": "complete",
  "artifacts": {
    "coherence": {
      "sonic_identity": "Warm documentary intimacy — close-mic room tone, organic textures, speech-first spectrum below 6 kHz",
      "primary_mood": "hopeful",
      "density": "sparse"
    },
    "palettes": [
      {
        "palette_id": "farm_morning_exterior",
        "theme_label": "Family farm morning",
        "keywords": ["farm", "pasture", "dawn", "grass"],
        "segment_ids": ["seg_018", "seg_019", "seg_022"],
        "ambient_description": "Dawn pasture twenty meters out: dry grass wind, distant bird every 10s, no close animals, loopable 8s bed, energy below 8 kHz, documentary realism.",
        "accent_description": "Soft mid-register rise-fall, 1.5s, no percussion",
        "avoid": ["comedy hits", "big trailer booms", "crowd chants"]
      }
    ]
  },
  "memory_updates": {
    "follow_up_investigations": []
  },
  "confidence": 0.84,
  "reasoning_summary": "One palette covers all farm-tagged segments; identity matches fireside one_on_one brief."
}
```

**Why:** `segment_ids` from manifest tags; rich `ambient_description`; `sonic_identity` is mix-ready prose.

---

## Good — multiple palettes with clear boundaries

- `palette_id: fintech_terminal` → segments with `topic_tags: ["trading_floor"]`
- `palette_id: founder_apartment` → segments with `topic_tags: ["early_days"]`
- No segment appears in two palettes.

---

## Good — investigation for unmapped theme

- Brief topic `"Supply chain resilience"` has segments but no acoustic tags yet.
- `follow_up_investigations`: `{ "kind": "theme_unmapped", "question": "No segment_ids for supply chain topic — segment_classification may need patch" }`.

---

## Good — nine atlas scenarios (concise reference)

Use one palette cluster per scenario; map `segment_ids` from manifest tags. `scenario_bucket` should match `understanding/sonic_context.json` → `scenario.atlas_bucket`.

| Scenario | `palette_id` hint | `ambient_description` posture | `accent_description` |
|----------|-------------------|------------------------------|-----------------|
| `one_on_one` | `intimate_room` | Dry close-mic room tone; loopable; no melody | Soft mid rise ≤1.5s |
| `panel` | `forum_neutral` | Minimal bed; avoid overlap segments | Single soft punctuation only |
| `fireside` | `warm_hearth` | Gentle air; no percussion | Slow swell; no hype |
| `technical_deep_dive` | `lab_neutral` | None or ultra-thin HVAC | Rare; non-dramatic |
| `media_profile` | `broadcast_clean` | Sparse; non-sensational | Broadcast-neutral bump |
| `debate` | `studio_dry` | No continuous bed | No conflict-escalating hits |
| `noisy_room` | *(skip beds)* | Prefer no bed — speech already masked | No bright risers |
| `dense_jargon` | `focus_air` | Minimal; no lyrical harmonic content | Short; non-melodic |
| `trauma_adjacent` | `quiet_support` | No bed on flagged segments | Forbidden on trauma segments |

**Example (`trauma_adjacent` — Good):**

```json
{
  "palette_id": "quiet_support",
  "segment_ids": ["seg_016"],
  "topic_tags": ["care", "safety"],
  "ambient_description": "Near-silent neutral room air only where explicitly safe; no rhythmic content.",
  "accent_description": "none on trauma-flagged segments"
}
```

---

## Bad — invented palette without segments

```json
{
  "palette_id": "space_exploration",
  "segment_ids": [],
  "topic_tags": ["innovation"]
}
```

**Why:** No manifest support; generic tag — lint rejects empty `segment_ids`.

---

## Bad — sonic_identity is generic

```json
{
  "sonic_identity": "Professional podcast sound",
  "primary_mood": "engaging"
}
```

**Why:** Not actionable for `sfx_prompt_craft` or mix contract; arbiter reject.

---

## Bad — trailer energy on trauma-adjacent brief

- `primary_mood: "triumphant"` + `accent_description: "epic cymbal swell"` when `content_brief.emotional_beats` includes grief segments.

**Why:** Violates [interview-scenario-atlas.md](../interview-scenario-atlas.md) `trauma_adjacent` sound posture.

---

## Bad — speech-like ambient description

> "A narrator says 'welcome to the farm' over wind sounds."

**Why:** Diegetic speech in bed request — policy block at craft stage; palettes must stay instrumental.

---

## Bad — one palette per segment

- 40 segments → 40 palettes with unique `palette_id` values.

**Why:** API spend explosion; violates coherence — reuse palette across same `topic_tags` cluster.
