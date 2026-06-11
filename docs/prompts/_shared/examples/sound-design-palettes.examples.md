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
      "density_class": "sparse"
    },
    "palettes": [
      {
        "palette_id": "farm_morning_exterior",
        "topic_tags": ["family_farm", "pasture"],
        "segment_ids": ["seg_018", "seg_019", "seg_022"],
        "ambient_description": "Dawn pasture twenty meters out: dry grass wind, distant bird every 10s, no close animals, loopable 8s bed, energy below 8 kHz, documentary realism.",
        "stinger_color": "soft mid-register rise-fall, 1.5s, no percussion"
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

**Why:** Not actionable for `elevenlabs_prompt_craft` or mix contract; arbiter reject.

---

## Bad — trailer energy on trauma-adjacent brief

- `primary_mood: "triumphant"` + `stinger_color: "epic cymbal swell"` when `content_brief.emotional_beats` includes grief segments.

**Why:** Violates [interview-scenario-atlas.md](../interview-scenario-atlas.md) `trauma_adjacent` sound posture.

---

## Bad — speech-like ambient description

> "A narrator says 'welcome to the farm' over wind sounds."

**Why:** Diegetic speech in bed request — policy block at craft stage; palettes must stay instrumental.

---

## Bad — one palette per segment

- 40 segments → 40 palettes with unique `palette_id` values.

**Why:** API spend explosion; violates coherence — reuse palette across same `topic_tags` cluster.
