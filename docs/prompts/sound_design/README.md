# Sound design prompts (BUILD-061–064)

**Pins:** `openai`, local MMAudio `/v1`, `pydub` — [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md). Code changes: **Context7** at lock versions.

Stage prompts for Wave 5 sound design. Full logic: [sound-design.md](../../cross-cutting/sound-design.md). MMAudio large_44k_v2 API and post-analysis: [local-audio-stack.md](../../cross-cutting/local-audio-stack.md).

| File | Stage |
|------|--------|
| [theme-palettes.system.txt](./theme-palettes.system.txt) | `sound_design_palettes` |
| [plan-flow1.system.txt](./plan-flow1.system.txt) | `sound_design_plan` |
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

## Assets elevate structure, not coverage theater

Every SFX/music asset here is a **mutation on the music/SFX/air axis** of the Shape mutation engine (soft bands: bed coverage 0.40–0.88, hinge stinger 0.3–1.0) — see [mastering-shape-engine.md § Shape as mutation engine](../../cross-cutting/mastering-shape-engine.md#shape-as-mutation-engine). A bed, stinger, or foley cue only earns its place if it makes the shape more legible (marks a hinge, fills a real dead-air gap, sells a payoff) — never to prove coverage of a checklist. Reject a plan asset that repeats the same gesture without new structural reason; that reads as `sfx_repetition`/`listener_fatigue` at the closed-loop polish and hard-delight (`sonic_weave`) stages downstream.
