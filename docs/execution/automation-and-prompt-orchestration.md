---
id: execution-auto-prompts
tier: both
status: spec
depends_on: [execution-readme]
---

# Automation and prompt orchestration

Default posture: **mostly automatic** pipeline from normalized audio to **master WAV/MP3** + manifest, with **LLM prompts** steering creative choices (tone, length, story shape) without hand-operating every ffmpeg flag.

**Library alignment:** which tools belong to which preset—and what **not** to build—is defined in [orchestration-component-map.md](orchestration-component-map.md), including the **canonical backbone DAG**. The orchestrator should **not** become an unconstrained agent rewriting that graph; it **parameterizes** allowed steps and their configs.

## Anti-patterns

- Letting the LLM invent **new pipeline stages** at runtime (unbounded scope creep).
- Hiding **high-risk** calls inside “generic tool” wrappers—every gated capability must expose a **stable tool id** for [high-risk-first-use-gating.md](high-risk-first-use-gating.md).

## Layers

1. **Machine prompts (frozen in repo):** segmentation defaults, salience rubric, EDL validation rules.
2. **User “session prompt” (once per interview or per preset):** e.g. “28 minutes, warm, minimize sadness, keep all stories about X.”
3. **Tool-calling plan:** the orchestrator proposes a **DAG of steps** (STT → score → pick → mux); LLM edits only **parameters** within allowed tools unless a **high-risk gate** fires ([high-risk-first-use-gating.md](high-risk-first-use-gating.md)). Optional **difficulty** tools such as `spectrogram_yolo11` and `wav2vec_embed` stay **named, versioned** calls that attach manifest annotations—never unnamed “run some CV” steps ([spectrogram-yolo-wav2vec-orchestration.md](spectrogram-yolo-wav2vec-orchestration.md)).

## What the user should not have to do

- Click per crossfade length.
- Manually type timestamps if word alignment exists.
- Re-enter API keys once profiles exist.

## When the system should surface a question

- Ambiguous **language** or **speaker** labels below confidence.
- **Mutually exclusive** story picks (see [difficult-segment-combinations.md](difficult-segment-combinations.md)).
- **Duration budget** impossible without dropping a `force_include` clip.
- **First invocation** of any component you marked **high-risk** for this machine/profile.

## Open decisions

- Single “**auto episode**” command vs chat-style loop for parameter tweaks.

## Links

- [orchestration-component-map.md](orchestration-component-map.md)
- [spectrogram-yolo-wav2vec-orchestration.md](spectrogram-yolo-wav2vec-orchestration.md)
- [../pipeline/scoring-and-selection/llm-assisted-ranking.md](../pipeline/scoring-and-selection/llm-assisted-ranking.md)
- [complexity-ladder-end-to-end-ideas.md](complexity-ladder-end-to-end-ideas.md)
