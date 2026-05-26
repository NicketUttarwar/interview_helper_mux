# Sound design prompts (planned — BUILD-061–064)

Implement as `*.system.txt` when executing [BUILD-060–066](../../build-out/README.md#wave-5--coherent-sound-design-planned). Full logic: [sound-design.md](../../cross-cutting/sound-design.md).

**Guardrails + edge cases (light, breadth-first):** [guardrails-and-edge-cases.md](./guardrails-and-edge-cases.md) — read before authoring prompts or mix validators.

---

## `theme-palettes.system.txt` (stage: `sound_design_palettes`)

**When:** After `segment_classification`.

**Inputs:** `content_brief`, `segments` (manifest), optional `analysis_state`.

**Output artifacts (partial SDP):** `coherence`, `palettes[]`; empty `assets`, `flow_plans`.

**Rules:**

- 1–4 palettes; each maps to ≥1 `segment_id` via `topic_tags` / brief topics.
- `ambient_description` = continuous low bed; `accent_description` = rare one-shot.
- `avoid` = clichés for this interview tone.
- Do not invent themes without transcript support.

---

## `plan-flow1.system.txt` (stage: `sound_design_plan_flow1`)

**When:** After `transitions`, before generate.

**Inputs:** SDP (palettes), `selection`, `narrative_plan`, `transitions`, `gap_report`, `segments`.

**Output:** `assets[]` (3–6), `flow_plans.flow1.cues[]`.

**Reuse rules:**

- One `chapter_stinger` asset → many `after_segment` cues.
- One `ambient_bed` per palette → many `under_segment` cues on matching segments.
- One `vo_bridge` asset for recorded VO lines.

**Placement:** `under_segment`, `after_segment`, `before_segment`; levels `level_db` / `duck_under_speech_db`.

---

## `plan-flow2.system.txt` (stage: `sound_design_plan_flow2`)

**When:** After `highlight_selection`.

**Inputs:** SDP, `selection` (highlights), `content_brief`.

**Output:** `assets[]` (2–4), `flow_plans.flow2.cues[]`.

**Reuse rules:**

- One `transition_stinger` asset → every `between_clips` cue (`from_clip_rank`, `to_clip_rank`).
- One `cold_open` at `before_timeline`.
- Optional `outro` at `after_timeline` (may share transition asset).

---

## `elevenlabs-prompt-craft.system.txt` (stage: `elevenlabs_prompt_craft`)

**When:** Inside generate step, before ElevenLabs API.

**Inputs:** `assets[]`, `coherence`.

**Output:** `artifacts.prompts[]` with `asset_id`, `elevenlabs_prompt`, `duration_seconds`, `negative_prompt`.

**Rules:**

- No voices, lyrics, or speech in prompts.
- Consistent with `sonic_identity`.
- Beds 4–8s; stingers 1–2.5s; accents <1.5s.
