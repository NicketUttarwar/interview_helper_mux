# LLM stage model matrix

**Status: spec only** — authoritative per-stage routing table for the smart-routing framework. v1 code uses flat `models.<stage_key>` strings in `config/app.defaults.json`; see [model-routing.md](./model-routing.md) for current runtime mapping.

**Hub:** [llm-orchestration.md](./llm-orchestration.md) · **Tiers:** [model-routing.md](./model-routing.md) · **Volley:** [context-padding.md](./context-padding.md) · **SDK pin:** [anchored-toolchain.md](./anchored-toolchain.md)

---

## Legend

| Column | Values |
|--------|--------|
| **Severity** | Editorial impact if this stage is wrong |
| **Default tier** | `economy` \| `standard` \| `flagship` for `task_kind=primary` |
| **Task kinds** | Which call types the stage uses in target architecture |
| **Volley** | `full` \| `shard` \| `collate` (primary uses full unless decomposing) |
| **Decompose** | Whether arbiter may trigger shard/collate |
| **Upgrade triggers** | When to bump tier or decompose |

---

## Shared analysis

| Stage key | Severity | Default tier | Task kinds | Volley | Decompose | Upgrade triggers | Prompt |
|-----------|----------|--------------|------------|--------|-----------|------------------|--------|
| `speaker_roles` | low | economy | primary, arbiter | full | no | systematic role inversion | [speaker-roles.system.txt](../prompts/understanding/speaker-roles.system.txt) |
| `content_context` | medium | economy | primary, arbiter | full | no | low confidence; thesis contradicts transcript tail | [content-context.system.txt](../prompts/understanding/content-context.system.txt) |
| `boundary_detection` | medium | standard | primary, arbiter, shard, collate | full / shard / collate | yes — segment batches | truncation; partial boundaries | [boundary-detection.system.txt](../prompts/segmentation/boundary-detection.system.txt) |
| `segment_classification` | medium | standard | primary, arbiter, shard, collate | full / shard / collate | yes — segment batches | `theme_unmapped`; max_segments hit | [segment-classification.system.txt](../prompts/segmentation/segment-classification.system.txt) |
| `missing_framing` | high | flagship | primary, arbiter, shard, collate | full / shard / collate | yes — segment batches | `max_gap_evaluations`; partial gap coverage | [missing-framing.system.txt](../prompts/interviewer-gap/missing-framing.system.txt) |
| `optimal_questions` | high | flagship | primary, arbiter | full | no | weak VO linkage to gaps | [optimal-questions.system.txt](../prompts/interviewer-gap/optimal-questions.system.txt) |

---

## Flow 1

| Stage key | Severity | Default tier | Task kinds | Volley | Decompose | Upgrade triggers | Prompt |
|-----------|----------|--------------|------------|--------|-----------|------------------|--------|
| `topic_coverage_audit` | high | flagship | primary, arbiter | full | no | coverage holes vs brief | [topic-coverage-audit.system.txt](../prompts/selection/topic-coverage-audit.system.txt) |
| `narrative_arc_plan` | high | flagship | primary, arbiter | full | no | chapter cap violations | [narrative-arc-plan.system.txt](../prompts/selection/narrative-arc-plan.system.txt) |
| `full_master_ranking` | high | flagship | primary, arbiter | full | no (future: theme clusters) | incoherent order vs arc | [full-master-ranking.system.txt](../prompts/selection/full-master-ranking.system.txt) |
| `transitions` | low | economy | primary, arbiter | full | no | tone mismatch only | [transitions.system.txt](../prompts/assembly/transitions.system.txt) |
| `podcast_sfx_brief` | low | economy | primary, arbiter | full | no | — | [podcast-sfx-brief.system.txt](../prompts/assembly/podcast-sfx-brief.system.txt) |

---

## Flow 2

| Stage key | Severity | Default tier | Task kinds | Volley | Decompose | Upgrade triggers | Prompt |
|-----------|----------|--------------|------------|--------|-----------|------------------|--------|
| `highlight_selection` | high | flagship | primary, arbiter | full | no | weak hook / over cap clips | [highlight-selection.system.txt](../prompts/selection/highlight-selection.system.txt) |
| `sfx_brief` | low | economy | primary, arbiter | full | no | — | [sfx-brief.system.txt](../prompts/assembly/sfx-brief.system.txt) |

---

## Flow 3

| Stage key | Severity | Default tier | Task kinds | Volley | Decompose | Upgrade triggers | Prompt |
|-----------|----------|--------------|------------|--------|-----------|------------------|--------|
| `podcast_show_description` | high | flagship | primary, arbiter | full | no | thin evidence; wrong person/voice; word count out of band | [podcast-show-description.system.txt](../prompts/publishing/podcast-show-description.system.txt) |

Rich **user/assistant** prior turns: `content_context`, `speaker_roles`, `segment_classification`, profile slice (`themes`, `narrative`, `style`, `major_questions`), optional gap summaries — [context-padding.md](./context-padding.md).

---

## Sound design (planned — BUILD-060+)

Per [sound-design.md](./sound-design.md). Not in v1 `models` map until stages ship.

| Stage key | Severity | Default tier | Task kinds | Volley | Decompose | Upgrade triggers | Prompt |
|-----------|----------|--------------|------------|--------|-----------|------------------|--------|
| `sound_design_palettes` | low | economy | primary, arbiter | full | no | — | [theme-palettes.system.txt](../prompts/sound_design/theme-palettes.system.txt) |
| `sound_design_plan_flow1` | high | flagship | primary, arbiter | full | no | density / palette mismatch | [plan-flow1.system.txt](../prompts/sound_design/plan-flow1.system.txt) |
| `sound_design_plan_flow2` | high | flagship | primary, arbiter | full | no | — | [plan-flow2.system.txt](../prompts/sound_design/plan-flow2.system.txt) |
| `elevenlabs_prompt_craft` | low | economy | primary, arbiter | full | no | policy / voice bleed | [elevenlabs-prompt-craft.system.txt](../prompts/sound_design/elevenlabs-prompt-craft.system.txt) |

---

## Internal / meta

| Stage key | Severity | Default tier | Task kinds | Volley | Decompose | Prompt |
|-----------|----------|--------------|------------|--------|-----------|--------|
| `_arbiter` | low | economy | arbiter only | minimal | no | [arbiter.system.txt](../prompts/_shared/arbiter.system.txt) |

---

## Task-kind tier rules (summary)

| `task_kind` | Tier |
|-------------|------|
| `arbiter` | economy (always) |
| `shard` | economy (always) |
| `collate` | max(stage default, standard) when severity = high; else stage default |
| `primary` | stage default tier; `retry_uptier` bumps one step |

---

## Decompose strategies by stage

| Stage | Strategy | `shard_plan` shape |
|-------|----------|-------------------|
| `boundary_detection` | Time ranges or segment index batches | `{ "label", "start_ms", "end_ms" }` or `segment_ids` |
| `segment_classification` | Segment batches (~`max_segments_in_context` each) | `{ "label", "segment_ids" }` |
| `missing_framing` | Gap evaluation batches (~`max_gap_evaluations` each) | `{ "label", "segment_ids" }` |

Max shards per attempt: **8** (see [llm-orchestration.md](./llm-orchestration.md)).

---

## v1 runtime note

Until smart routing is implemented, `get_model(stage_key)` ignores `task_kind` and returns the flat string from `config/app.defaults.json`. Committed defaults may differ from `config/templates/app.defaults.json` for segmentation stages — see [model-routing.md](./model-routing.md#config-drift).
