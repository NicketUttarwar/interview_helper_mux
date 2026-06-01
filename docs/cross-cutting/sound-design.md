# Coherent sound design (shipped)

**Status:** Wave 5 shipped — SDP palettes + flow plans, ElevenLabs craft/generate per `asset_id`, and `mix_flow1` / `mix_flow2` (BUILD-060–066). Legacy v1 brief stages (`podcast_sfx_brief`, `sfx_brief`) remain for single-stage rerun only; default pipeline uses SDP + mix. Stage ids: [stage-registry.md](../build-out/stage-registry.md). Remaining quality gaps: [podcast-quality-roadmap.md](./podcast-quality-roadmap.md).

**Build tickets:** [Wave 5 — done](../build-out/README.md#wave-5--coherent-sound-design-done)

**Prompt-stage guardrails:** [prompts/sound_design/guardrails-and-edge-cases.md](../prompts/sound_design/guardrails-and-edge-cases.md)

**ElevenLabs canonical guide:** [elevenlabs-integration-guide.md](./elevenlabs-integration-guide.md) — API, spend, post-analysis, doc inventory.

**Toolchain:** [anchored-toolchain.md](./anchored-toolchain.md) (`pydub`, `ffmpeg`, ElevenLabs `/v1`, `openai` for craft stages).

**Prompt files (Wave 5):** [theme-palettes](../prompts/sound_design/theme-palettes.system.txt), [plan-flow1](../prompts/sound_design/plan-flow1.system.txt), [plan-flow2](../prompts/sound_design/plan-flow2.system.txt), [elevenlabs-prompt-craft](../prompts/sound_design/elevenlabs-prompt-craft.system.txt). Examples: [sound-design.examples.md](../prompts/_shared/examples/sound-design.examples.md).

**Per-interview acoustic baseline (shipped, BUILD-082):** [source-derived-sonic-mix-profile.md](./source-derived-sonic-mix-profile.md) — `understanding/source_acoustic_profile.json` feeds `coherence`, craft volleys, and mix contract.

---

## Problem with v1

| Gap | Impact |
|-----|--------|
| SFX chosen only at end of flow | Misses themes from `content_brief`, segment `topic_tags`, VO placement |
| One new WAV per brief line | No sonic cohesion; montage sounds unrelated |
| Fixed 2s ElevenLabs duration | Ignores `duration_ms` in brief |
| Flow 2 concat by `sfx_001` index | Cold open after clip 0; ignores `from_clip_rank` |
| Flow 1 mux ignores SFX + VO | Generated files unused |
| Ducking / beds in prompts only | Never applied in mix |

---

## North star

Sound design is a **timeline artifact**, not a one-shot JSON before export:

1. **Discover** sonic opportunities during analysis (themes, entities, beats, gaps, VO).
2. **Plan** when, where, why, and how loud — with **reusable `asset_id`s**.
3. **Craft** ElevenLabs prompts via OpenAI (shared sonic identity).
4. **Generate** one file per `asset_id` (same WAV referenced by many cues).
5. **Mix** with ducking, semantic placement, VO bridges.

Example: interview about **farming** → palette `farming` maps to segments tagged `farming` → one `ambient_farm_morning` asset looped under those segments; one `chapter_stinger_warm` reused at every chapter end.

---

## Sound Design Plan (SDP)

Primary file: `understanding/sound_design_plan.json`

Supporting:

| Path | Purpose |
|------|---------|
| `sound_design/assets/{asset_id}.wav` | One generated file per reusable asset |
| `sound_design/elevenlabs_prompts.json` | Crafted prompts per asset (audit) |
| `flow_1_master/podcast_sfx_brief.json` | Legacy export (optional compat) |
| `flow_2_highlights/sfx_brief.json` | Legacy export (optional compat) |

### Document shape

```json
{
  "version": 1,
  "coherence": {
    "sonic_identity": "warm documentary, understated",
    "primary_mood": "hopeful",
    "density": "sparse"
  },
  "palettes": [
    {
      "palette_id": "farming",
      "theme_label": "Family farm operations",
      "keywords": ["farm", "crops", "barn"],
      "segment_ids": ["seg_018", "seg_019", "seg_022"],
      "ambient_description": "soft morning pasture, distant birds, no voices",
      "accent_description": "single distant horse snort, rare",
      "avoid": ["cartoon barn", "comedy animals"]
    }
  ],
  "assets": [
    {
      "asset_id": "chapter_stinger_warm",
      "role": "chapter_stinger",
      "description": "soft tonal rise, 1.5s",
      "duration_seconds": 1.5,
      "reuse_note": "Same stinger after every chapter"
    },
    {
      "asset_id": "ambient_farm_morning",
      "role": "ambient_bed",
      "palette_id": "farming",
      "description": "loopable field ambience",
      "duration_seconds": 6.0
    }
  ],
  "flow_plans": {
    "flow1": {
      "profile": "podcast",
      "cues": [
        {
          "cue_id": "bed_seg_018",
          "asset_id": "ambient_farm_morning",
          "placement": "under_segment",
          "segment_id": "seg_018",
          "level_db": -28,
          "duck_under_speech_db": 16
        },
        {
          "cue_id": "sting_ch02",
          "asset_id": "chapter_stinger_warm",
          "placement": "after_segment",
          "after_segment_id": "seg_025",
          "chapter_id": "ch_02"
        }
      ]
    },
    "flow2": {
      "profile": "montage",
      "cues": [
        {
          "cue_id": "cold_open",
          "asset_id": "montage_rise_hit",
          "placement": "before_timeline"
        },
        {
          "cue_id": "trans_1_2",
          "asset_id": "montage_whoosh_soft",
          "placement": "between_clips",
          "from_clip_rank": 1,
          "to_clip_rank": 2
        }
      ]
    }
  },
  "generated": {
    "chapter_stinger_warm": "sound_design/assets/chapter_stinger_warm.wav"
  }
}
```

### Asset roles

| Role | Reuse pattern | Flow |
|------|---------------|------|
| `ambient_bed` | One per palette; many `under_segment` cues | Flow 1 |
| `chapter_stinger` | One asset; all chapter boundaries | Flow 1 |
| `vo_bridge` | One asset; all VO intro/outro | Flow 1 |
| `transition_stinger` | **One asset between every clip pair** | Flow 2 |
| `cold_open` / `outro` | Once each (may share asset with transition) | Flow 2 |
| `accent_foley` | Sparse; optional | Either |

**Rule:** Multiple cues → same `asset_id` → one ElevenLabs generation → coherent master.

---

## When stages run (multi-phase)

Do not limit SFX to the final assembly step. Information accrues; **plan early, generate late**.

```mermaid
flowchart TB
  CC[content_context] --> PAL[sound_design_palettes]
  SC[segment_classification] --> PAL
  PAL --> SDP[(sound_design_plan.json)]
  G1[G1 VO pickup] --> VO[vo_ingest]
  VO --> VO_CUES[VO bridge cues]
  G2[G2 flow] --> FPLAN[flow plan stage]
  FPLAN --> SDP
  SDP --> CRAFT[elevenlabs_prompt_craft]
  CRAFT --> GEN[generate per asset_id]
  GEN --> MIX[mix_flow1 / mix_flow2]
```

| Phase | Stage key | Inputs | Writes |
|-------|-----------|--------|--------|
| A | `sound_design_palettes` | `content_brief`, `segments`, `analysis_state`, `source_acoustic_profile` | `palettes`, `coherence` |
| B | `sound_design_plan_flow1` or `_flow2` | SDP, selection, narrative, gaps, transitions | `assets`, `flow_plans.*.cues` |
| C | *(optional)* `sound_design_vo_finalize` | SDP + `vo_pickup` durations | Adjust VO bridge cues |
| D | `sound_design_generate_flow*` | SDP assets | `sound_design/assets/*.wav` |
| E | `mux_flow*` | SDP + EDL/selection + VO | `assembly.wav` |

**Gate (shipped, optional):** **G1.5** — when `g1_5_require_prompt_approval: true`, operator reviews cue list / prompt craft before ElevenLabs spend ([operator-gates.md](../workflows/operator-gates.md#g15--sound-design-prompt-approval-optional-shipped)).

---

## LLM stages and prompts

| Stage | Model tier (target) | Prompt file |
|-------|---------------------|-------------|
| `sound_design_palettes` | economy | [theme-palettes.system.txt](../prompts/sound_design/theme-palettes.system.txt) |
| `sound_design_plan_flow1` | flagship | [plan-flow1.system.txt](../prompts/sound_design/plan-flow1.system.txt) |
| `sound_design_plan_flow2` | flagship | [plan-flow2.system.txt](../prompts/sound_design/plan-flow2.system.txt) |
| `elevenlabs_prompt_craft` | economy | [elevenlabs-prompt-craft.system.txt](../prompts/sound_design/elevenlabs-prompt-craft.system.txt) |

Full matrix: [llm-stage-model-matrix.md](./llm-stage-model-matrix.md).

### Palette stage (analysis)

- After `segment_classification`.
- Map `content_brief.topics` + `topic_tags` → thematic palettes (farm, fintech, etc.).
- No generation yet; no cues.

### Flow 1 plan

- Require **3–6 assets**; chapter stinger **reused** at every chapter.
- Beds `under_segment` only where palette `segment_ids` match.
- VO bridges from `gap_report` (`delivery: record`) → `before_segment` / `after_segment` cues.
- Subtle podcast — no trailer whooshes.

### Flow 2 plan

- Require **2–4 assets**; **one transition asset** for all `between_clips` cues.
- Cold open `before_timeline`; optional outro `after_timeline`.
- Energy via `level_db`, not unrelated SFX per cut.

### ElevenLabs prompt craft

- Input: `assets[]` + `coherence`.
- Output per asset: `elevenlabs_prompt`, `duration_seconds`, `negative_prompt` (no voices/lyrics).
- Ensures consistent “library” timbre before API calls.

---

## Generation (`sound_design/generate`)

For each unique `asset_id` referenced by active flow cues:

1. Run prompt craft (if not cached in `elevenlabs_prompts.json`).
2. `POST https://api.elevenlabs.io/v1/music` via `interview_mux.elevenlabs_rest.generate_music` (`prompt`, `music_length_ms`, `model_id`: `music_v2`, `force_instrumental`; craft `prompt_influence` mapped to prompt prose).
3. Write `sound_design/assets/{asset_id}.wav` (normalize to mono 48 kHz WAV if API returns MPEG).

**Tuning / QA:** [elevenlabs-prompt-influence-tuning.md](./elevenlabs-prompt-influence-tuning.md) · [elevenlabs-prompt-regression.md](../prompts/_shared/examples/elevenlabs-prompt-regression.md)
4. On failure → silent ffmpeg placeholder (length from `duration_seconds`).
5. Skip regen if file exists and `generated[asset_id]` unchanged (idempotent reruns).

**Not** one file per cue (`sfx_001`, `sfx_002`).

---

## Musical structure for ElevenLabs prompts

Musical language in prompts must serve **speech-first podcast clarity**, not standalone music production.

### musical_intent schema (craft stage)

Stored on each row in `sound_design/elevenlabs_prompts.json` when the asset uses pitch motion:

| Field | Values | Default for beds |
|-------|--------|------------------|
| `register` | `low` \| `mid` \| `high` | N/A (beds omit musical_intent) |
| `motion` | `static` \| `rise` \| `fall` \| `rise_then_fall` | — |
| `tonal_center` | `unspecified_warm` \| `unspecified_neutral` \| `none` | — |
| `harmonic_density` | `none` \| `sparse` \| `moderate` | `none` for beds |
| `rhythmic_presence` | `none` \| `pulse` | **`none`** always for beds |
| `tempo_feel_bpm` | number or null | `null` |
| `meter_feel` | `free` \| `even` \| `swung` | `free` |

### Podcast-safe defaults

- **Beds:** No pitch center, no meter, no pulse — only environmental spectrum and motion (wind, room).
- **Chapter stingers:** At most **one** pitch gesture over ≤2 s; prefer noise+filter sweep over diatonic melody.
- **Montage transitions:** Forward spectral motion; avoid memorable melodic hooks listeners would hum.
- **Midrange discipline:** Stingers and transitions keep energy out of 1–4 kHz when they might overlap speech tails.

### Role-specific musical constraints

| Role | Allowed | Forbidden |
|------|---------|-----------|
| `ambient_bed` | Aperiodic texture, rare non-pitched events | Beat, chord progression, hook |
| `chapter_stinger` | Single rise/fall, sparse partials | Drum kit, long riser >1.5 s |
| `transition_stinger` | Brief sweep, noise burst | Vocal-like formants, EDM build |
| `cold_open` | Slightly stronger gesture than transition | Lyrics, chant, recognizable tune |
| `vo_bridge` | High-passed air only | Any pitch competing with VO formants |

Craft prompts must **verbalize** these constraints in prose even when `musical_intent` is present — the API receives `elevenlabs_prompt` text only.

---

## Post-generation analysis and adaptive placement

**Status:** Operator workflow (post-listen QA). Mix placement and ducking ship in `sound_design.py` (`mix_flow1`, `mix_flow2`).

Initial ElevenLabs output is a **candidate**. Final timeline placement uses analysis **after** generation against interview themes, keywords, operator notes (`style.sound_design_notes`), and the speech stem.

### Workflow

```mermaid
flowchart LR
  GEN[Generate_assets] --> LISTEN[Listen_per_asset]
  LISTEN --> FIT{Theme_and_speech_fit?}
  FIT -->|no| REGEN[Regen_or_replace]
  FIT -->|yes| CUE[Map_cues_to_timeline]
  CUE --> ADAPT[Adapt_overlap_duck_crossfade]
  ADAPT --> MUX[Mix_flow1_or_flow2]
```

### Phase 1 — Per-asset fit

| Check | Method | Fail |
|-------|--------|------|
| Theme fit | Compare asset timbre to palette keywords + `sonic_identity` | Regen (max 2) |
| Intelligibility | Bed under densest speech segment | Lower level / stronger duck |
| Duration | Tail vs cue window | Adjust `duration_seconds` |
| Policy | Voice-like content | Discard; tighten negative_prompt |
| Loop seam | Bed loop in DAW | Regen with seamless-wrap language |

**Inputs:** `content_brief`, `analysis_state.themes`, `segments.manifest`, generated WAV, `ingest/normalized.wav` or `assembly_preview.wav`. Planned: `source_acoustic_profile` — [source-derived-sonic-mix-profile.md](./source-derived-sonic-mix-profile.md).

### Phase 2 — Transition adaptation (decided here, not in plan stage)

| Pattern | Use when | Typical params |
|---------|----------|----------------|
| Sequential | Stinger after clean speech tail | 50–150 ms gap optional |
| Overlap + duck | Bed under segment | Bed −26 to −30 dB; duck 14–20 dB |
| Equal-power crossfade | Flow 2 clip change | 80–200 ms |
| Fade under | VO enters over bed | Bed −3 dB/s over 300 ms |
| Layer + attenuate | Cold open into clip 1 | Open −6 to −12 dB over 400 ms |

**Flow 1:** Longer bed fades at chapters; stingers **after** words, not over them.

**Flow 2:** Shorter crossfades; one transition asset; level_db tweaks per cue only.

### Phase 3 — Operator gate

Log approve / regen / level change in `gui_log.jsonl`. When enabled, G1.5 (`g1_5_require_prompt_approval`) covers **pre-spend** prompt review; this phase is **post-listen**.

Full playbook: [elevenlabs-integration-guide.md § Post-generation](./elevenlabs-integration-guide.md#post-generation-analysis-and-adaptive-placement).

---

## Mix logic

Module: `src/interview_mux/sound_design.py` (`mix_flow1`, `mix_flow2`).

### Flow 1 (`mix_flow1`)

Timeline order per `ordered_segment_ids`:

1. Optional VO bridge stinger (`before_segment`).
2. Recorded VO from `vo_pickup/{line_id}.wav`.
3. Speech clip from `ingest/normalized.wav`.
4. Overlay `ambient_bed` assets (`pydub` loop + duck under speech).
5. Chapter stinger (`after_segment`) — **same WAV each time**.
6. VO after segment if `placement: after`.

### Flow 2 (`mix_flow2`)

1. Cold open asset (`before_timeline`).
2. For each highlight (by `rank`): clip WAV → **same** transition asset (`between_clips`).
3. Optional outro (`after_timeline`).

Use `from_clip_rank` / `to_clip_rank` on cues — not concat index.

---

## Analysis inputs to use

| Source | Use for |
|--------|---------|
| `content_brief.topics`, `emotional_beats` | Palettes, mood |
| `analysis_state.themes`, `entities` | Keywords, avoid list |
| `source_acoustic_profile` | `pace_class`, `mix_contract`, `prompt_tokens` |
| `segments.manifest` + `topic_tags` | Segment ↔ palette mapping |
| `gap_report` + `vo_pickup` | VO bridge cues, timing |
| `narrative_plan`, `selection.chapters` | Chapter stingers |
| `style` in analysis profile | Density, podcast vs montage |

---

## Legacy v1 vs default path (summary)

| Area | Legacy v1 (single-stage rerun) | Default (shipped) |
|------|-------------------------------|-------------------|
| Planning | `podcast_sfx_brief` / `sfx_brief` at end | SDP + palettes + flow plans |
| Reuse | Per-cue `sfx/*.wav` | `asset_id` → one WAV |
| Thematic beds | Prompt only | `under_segment` + palette map |
| ElevenLabs | Raw `description`, 2s fixed | Crafted prompt + variable duration |
| Flow 1 mix | `mux_flow1` alias / legacy concat | `mix_flow1` — speech + VO + beds + stingers |
| Flow 2 mix | Index-based `sfx_i` | `mix_flow2` — cold open + shared transition |

---

## Operator / config

```json
"sound_design": {
  "enabled": true,
  "max_assets_flow1": 6,
  "max_assets_flow2": 4,
  "allow_diegetic_ambient": true,
  "g1_5_require_prompt_approval": false
}
```

Add `style.sound_design_notes` to `analysis_state.json` for operator overrides (density, banned sounds).

---

## Related

- [elevenlabs-integration-guide.md](./elevenlabs-integration-guide.md) — canonical ElevenLabs API + operations
- [sound-design.examples.md](../prompts/_shared/examples/sound-design.examples.md) — worked prompts
- v1 prompts: `docs/prompts/assembly/podcast-sfx-brief.system.txt`, `sfx-brief.system.txt`
- v1 code: `sfx_elevenlabs.py`, `selection_flow1.py`, `assembly_flow1.py`, `assembly_flow2.py`
- [analysis-memory.md](./analysis-memory.md) — profile feeds all LLM stages
- [artifact-layout.md](./artifact-layout.md) — run folder layout (SDP path + schema link)
