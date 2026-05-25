# Prompt tree

Prompts are organized by **pipeline stage**. Each `.system.txt` file is a stage template; runtime prepends [`_shared/analysis-preamble.system.txt`](./_shared/analysis-preamble.system.txt) for all LLM calls.

User messages include **analysis memory** (`analysis_state_summary`, `open_investigations`) plus `stage_input`. See [analysis-memory.md](../cross-cutting/analysis-memory.md) and [analysis-stage-matrix.md](./analysis-stage-matrix.md).

## Tree

```
prompts/
├── README.md
├── _shared/
│   ├── analysis-preamble.system.txt    ← envelope + memory rules (all LLM stages)
│   └── examples/                       ← few-shot reference (gap detection, VO lines)
├── understanding/
│   ├── content-context.system.txt
│   └── speaker-roles.system.txt
├── segmentation/
│   ├── boundary-detection.system.txt
│   └── segment-classification.system.txt
├── interviewer-gap/
│   ├── missing-framing.system.txt
│   └── optimal-questions.system.txt
├── selection/
│   ├── topic-coverage-audit.system.txt
│   ├── narrative-arc-plan.system.txt
│   ├── full-master-ranking.system.txt
│   └── highlight-selection.system.txt
├── assembly/
│   ├── transitions.system.txt
│   ├── podcast-sfx-brief.system.txt   ← v1 SFX brief
│   └── sfx-brief.system.txt           ← v1 montage brief
└── sound_design/                      ← planned (BUILD-061–064); see README there
    └── README.md
```

## Invocation order

### Analysis phase (`run_analysis.py`)

Orchestrator: inner retries per stage + investigation queue drain. See [analysis-orchestration-loop.md](../workflows/analysis-orchestration-loop.md).

1. `understanding/speaker-roles`
2. `understanding/content-context`
3. `segmentation/boundary-detection`
4. `segmentation/segment-classification`
5. *(planned)* `sound_design/theme-palettes` — after classification
6. `interviewer-gap/missing-framing`
7. `interviewer-gap/optimal-questions`

**Gate G1** — human VO for `delivery: record`

**Gate G2** — operator picks `flow1` or `flow2`

### Flow phase (`run_flow.py`)

Flow stages use the same envelope; read memory but single pass (no inner loop).

**Flow 1:** topic-coverage → narrative-arc → full-master-ranking → transitions → podcast-sfx-brief *(v1)*

**Flow 2:** highlight-selection → sfx-brief *(v1)*

**Planned (BUILD-060+):** palettes in analysis → `sound_design/plan-flow*` → generate per `asset_id` → mix — [sound-design.md](../cross-cutting/sound-design.md)

## Conventions

- All LLM responses use the [analysis envelope](../cross-cutting/json-schemas/analysis_envelope.schema.json); stage JSON goes in `artifacts`.
- Per-stage artifact schemas: [`json-schemas/artifacts/`](../cross-cutting/json-schemas/artifacts/) — validated in Python via `interview_mux.prompt_validation`.
- Runtime injects **pipeline thresholds** from `config/app.defaults.json` → `analysis.prompt_thresholds` (pause ms, word limits, max chapters/clips).
- Each stage prompt includes **memory sync**, **investigations**, and **do not** rules where applicable.
- Few-shot references: [`_shared/examples/`](./_shared/examples/).
- Never embed secrets in prompt files.
- Operator-edited `analysis_state.json` is authoritative when `meta.operator_verified` is true.
- Keep interviewer lines **short** — [logic-tree.md](../logic-tree.md).

## Output schemas

- [analysis_state.schema.json](../cross-cutting/json-schemas/analysis_state.schema.json)
- [analysis_envelope.schema.json](../cross-cutting/json-schemas/analysis_envelope.schema.json)
- [segment.schema.json](../cross-cutting/json-schemas/segment.schema.json)

Shared segment reference (in `stage_input` / manifest):

```json
{
  "segment_id": "seg_001",
  "start_ms": 0,
  "end_ms": 12400,
  "speaker_id": "spk_01",
  "speaker_role": "interviewee",
  "type": "interviewee_answer",
  "text": "...",
  "topic_tags": ["origin_story"]
}
```
