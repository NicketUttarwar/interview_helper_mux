# Prompt tree

**Implementers:** Python/OpenAI client behavior must match [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md) (lock + `pip-audit` + **Context7** at pinned package versions). Model API IDs: [model-routing.md](../cross-cutting/model-routing.md).

Prompts are organized by **pipeline stage**. Each `.system.txt` file is a stage template; runtime prepends [`_shared/analysis-preamble.system.txt`](./_shared/analysis-preamble.system.txt) for all LLM calls.

User messages include **analysis memory** (`analysis_state_summary`, `open_investigations`) plus `stage_input`. When an on-disk artifact already exists, `stage_input` also includes **`gap_fill_context`** (gaps to fill, skip_fields, existing snapshot) — [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md). See [analysis-memory.md](../cross-cutting/analysis-memory.md) and [analysis-stage-matrix.md](./analysis-stage-matrix.md).

**Routing:** v2 has no arbiter or shard/collate routing. Every stage goes through `llm_simple.py`: one structured call, one retry on schema failure, then hard stop. The `arbiter.system.txt` prompt and rubrics under `_shared/arbiter-rubrics/` are heritage — see [../v2/drop-manifest.md](../v2/drop-manifest.md).

## Tree

```
prompts/
├── README.md
├── mastering/                          ← Mastering Process contracts (mint/edit/shape/synthesize)
├── _shared/
│   ├── analysis-preamble.system.txt    ← envelope + memory + gap-fill rules (all LLM stages)
│   ├── arbiter.system.txt            ← heritage; arbiter routing removed in v2
│   └── examples/                       ← good vs bad pattern packs (*.examples.md)
├── understanding/
│   ├── content-context.system.txt
│   ├── content-brief-reanchor.system.txt
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
├── publishing/
│   └── podcast-show-description.system.txt  ← Flow 3 show blurb
└── sound_design/                      ← BUILD-061–064 (Wave 5)
    ├── README.md
    ├── theme-palettes.system.txt
    ├── plan-flow1.system.txt
    ├── sfx-prompt-craft.system.txt
    └── guardrails-and-edge-cases.md
```

## Example packs

Markdown “good vs bad” references under [`_shared/examples/`](./_shared/examples/). Each stage `.system.txt` that has a pack links to it (same pattern as gap stages).

Runtime compact injection is intentionally narrower than this reference list: by default only `content_context`, `missing_framing`, `segment_classification`, and `topic_coverage_audit` receive a capped excerpt from their example packs. Other packs are authoring and regression references unless `analysis.prompt_examples.stages` is configured.

| Stage / area | Example file |
|--------------|----------------|
| Speaker roles | [speaker-roles.examples.md](./_shared/examples/speaker-roles.examples.md) |
| Content brief | [content-context.examples.md](./_shared/examples/content-context.examples.md) |
| Boundary detection | [boundary-detection.examples.md](./_shared/examples/boundary-detection.examples.md) |
| Segment classification | [segment-classification.examples.md](./_shared/examples/segment-classification.examples.md) |
| Missing framing | [missing-framing.examples.md](./_shared/examples/missing-framing.examples.md) |
| Optimal questions | [optimal-questions.examples.md](./_shared/examples/optimal-questions.examples.md) |
| Topic coverage audit | [topic-coverage-audit.examples.md](./_shared/examples/topic-coverage-audit.examples.md) |
| Narrative arc plan | [narrative-arc-plan.examples.md](./_shared/examples/narrative-arc-plan.examples.md) |
| Full master ranking | [full-master-ranking.examples.md](./_shared/examples/full-master-ranking.examples.md) |
| Highlight selection | [highlight-selection.examples.md](./_shared/examples/highlight-selection.examples.md) |
| Podcast show description | [podcast-show-description.examples.md](./_shared/examples/podcast-show-description.examples.md) |
| Transitions | [transitions.examples.md](./_shared/examples/transitions.examples.md) |
| Podcast + montage SFX briefs | [sfx-briefs.examples.md](./_shared/examples/sfx-briefs.examples.md) |
| Sound design + MMAudio prompt craft | [sound-design.examples.md](./_shared/examples/sound-design.examples.md) |
| MMAudio regression (golden prompts) | [sfx-prompt-regression.md](./_shared/examples/sfx-prompt-regression.md) |
| Sound design (guardrails) | [sound_design/guardrails-and-edge-cases.md](./sound_design/guardrails-and-edge-cases.md) |

**Guard:** When you change rules in a `.system.txt`, update the matching `.examples.md` in the same PR. For **sound_design**, also see [local-audio-stack.md](../cross-cutting/local-audio-stack.md).

## Invocation order

### Analysis phase (`run_analysis.py`)

Linear stage order, max 2 attempts per stage. Canonical order: [`src/interview_mux/v2/config.py`](../../src/interview_mux/v2/config.py).

1. `understanding/speaker-roles` *(after `source_acoustic_profile` in pipeline)*
2. `understanding/content-context` — pass 1 semantic brief
3. `segmentation/boundary-detection`
4. `segmentation/segment-classification`
5. `understanding/content-brief-reanchor` — patch brief to timeline + topic links
6. `sound_design/theme-palettes` — `sound_design_palettes` after reanchor
7. `interviewer-gap/missing-framing`
8. `interviewer-gap/optimal-questions`

**Gate G1** — human VO for `delivery: record`

**Gate G2** — operator picks `flow1`, `flow2`, or `flow3`

### Flow phase (`run_flow.py`)

Flow stages use the same envelope; read memory but single pass (no inner loop).

**Flow 1:** topic-coverage → narrative-arc → full-master-ranking → transitions → `sound_design/plan-flow1` → `edl_narrative_audit` → `edl` → assembly preview → `sfx_prompt_craft` → generate → **`mix`** → master

**Flow 2:** highlight-selection → `sound_design/plan-flow2` → `sfx_prompt_craft` → generate → **`REMOVED_mix_flow2`** → master

**Flow 3:** `publishing/podcast-show-description` → `REMOVED_export_show_description`

Legacy v1 brief stages (`podcast-sfx-brief`, `sfx-brief`) and `mux_flow*` remain for single-stage rerun only. Default path: [sound-design.md](../cross-cutting/sound-design.md) · [stage-contracts/00-INDEX.md](../cross-cutting/stage-contracts/00-INDEX.md).

## Conventions

- All LLM responses use the [analysis envelope](../cross-cutting/json-schemas/analysis_envelope.schema.json); stage JSON goes in `artifacts`.
- Per-stage artifact schemas: [`json-schemas/artifacts/`](../cross-cutting/json-schemas/artifacts/) — validated in Python via `interview_mux.prompt_validation`.
- Runtime injects **pipeline thresholds** from `config/app.defaults.json` → `analysis.prompt_thresholds` (pause ms, word limits, max chapters/clips).
- Each stage prompt includes **memory sync**, **investigations**, and **do not** rules where applicable.
- Few-shot references: [`_shared/examples/`](./_shared/examples/) — see [Example packs](#example-packs).
- Never embed secrets in prompt files.
- Operator-edited `analysis_state.json` is authoritative when `meta.operator_verified` is true.
- Keep interviewer lines **short** — [logic-tree.md](../logic-tree.md).

## Output schemas

- [analysis_state.schema.json](../cross-cutting/json-schemas/analysis_state.schema.json)
- [analysis_envelope.schema.json](../cross-cutting/json-schemas/analysis_envelope.schema.json)
- [segment.schema.json](../cross-cutting/json-schemas/segment.schema.json)
- [json-schema-coverage.md](../cross-cutting/json-schema-coverage.md) — stage validation map + missing-contract checklist

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
