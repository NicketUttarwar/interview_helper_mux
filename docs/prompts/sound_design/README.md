# Sound design prompts (BUILD-061–064)

**Pins:** `openai`, local MMAudio `/v1`, `pydub` — [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md). Code changes: **Context7** at lock versions.

Stage prompts for Wave 5 sound design. Full logic: [sound-design.md](../../cross-cutting/sound-design.md). MMAudio large_44k_v2 API and post-analysis: [local-audio-stack.md](../../cross-cutting/local-audio-stack.md).

| File | Stage |
|------|--------|
| [theme-palettes.system.txt](./theme-palettes.system.txt) | `sound_design_palettes` |
| [plan-flow1.system.txt](./plan-flow1.system.txt) | `sound_design_plan` |
| [plan-flow2.system.txt](./plan-flow2.system.txt) | `REMOVED_sdp_flow2` |
| [sfx-prompt-craft.system.txt](./sfx-prompt-craft.system.txt) | `sfx_prompt_craft` |
| [sfx-prompt-refine.system.txt](./sfx-prompt-refine.system.txt) | `sfx_prompt_refine` |

**Examples:** [_shared/examples/sound-design.examples.md](../_shared/examples/sound-design.examples.md)

**Guardrails:** [guardrails-and-edge-cases.md](./guardrails-and-edge-cases.md)

---

## Stage summaries

See each `*.system.txt` for full rules. Brief:

- **Palettes** — Rich `ambient_description` / `accent_description`; 1–4 palettes; transcript-grounded `segment_ids`.
- **Plan Flow 1** — 3–6 assets; mandatory reuse; beds + chapter stingers + VO bridges.
- **Plan Flow 2** — 2–4 assets; one shared transition; cold open / outro.
- **Prompt craft** — 80–220 word verbal prompts; `musical_intent` for pitched stingers; strong `negative_prompt`.
- **Prompt refine** — revise failed assets only; preserve duration and speech/vocal bans while fixing QA/listen regressions.

Post-generation placement (duck, crossfade, overlap) is **not** fixed in plan stages — see [sound-design.md § Post-generation](../../cross-cutting/sound-design.md#post-generation-analysis-and-adaptive-placement).
