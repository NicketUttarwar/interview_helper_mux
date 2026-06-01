# Sound design prompts (BUILD-061–064)

**Pins:** `openai`, ElevenLabs REST `/v1`, `pydub` — [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md). Code changes: **Context7** at lock versions.

Stage prompts for Wave 5 sound design. Full logic: [sound-design.md](../../cross-cutting/sound-design.md). ElevenLabs Music v2 API and post-analysis: [elevenlabs-integration-guide.md](../../cross-cutting/elevenlabs-integration-guide.md).

| File | Stage |
|------|--------|
| [theme-palettes.system.txt](./theme-palettes.system.txt) | `sound_design_palettes` |
| [plan-flow1.system.txt](./plan-flow1.system.txt) | `sound_design_plan_flow1` |
| [plan-flow2.system.txt](./plan-flow2.system.txt) | `sound_design_plan_flow2` |
| [elevenlabs-prompt-craft.system.txt](./elevenlabs-prompt-craft.system.txt) | `elevenlabs_prompt_craft` |

**Examples:** [_shared/examples/sound-design.examples.md](../_shared/examples/sound-design.examples.md)

**Guardrails:** [guardrails-and-edge-cases.md](./guardrails-and-edge-cases.md)

---

## Stage summaries

See each `*.system.txt` for full rules. Brief:

- **Palettes** — Rich `ambient_description` / `accent_description`; 1–4 palettes; transcript-grounded `segment_ids`.
- **Plan Flow 1** — 3–6 assets; mandatory reuse; beds + chapter stingers + VO bridges.
- **Plan Flow 2** — 2–4 assets; one shared transition; cold open / outro.
- **Prompt craft** — 80–220 word verbal prompts; `musical_intent` for pitched stingers; strong `negative_prompt`.

Post-generation placement (duck, crossfade, overlap) is **not** fixed in plan stages — see [sound-design.md § Post-generation](../../cross-cutting/sound-design.md#post-generation-analysis-and-adaptive-placement).
