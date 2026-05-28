# Publishing copy (Flow 3)

**LLM stack:** [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md) · [model-routing.md](../../cross-cutting/model-routing.md)

Text deliverable for podcast distribution — no audio mux.

## Intent

Produce a **~200-word, third-person show description** that hooks listeners and accurately reflects the interview. Output is for podcast apps, websites, newsletters, and social link previews.

## When it runs

After shared analysis and **gate G2** when `run_meta.json` has `selected_flow: flow3`. Does not require Flow 1 ranking or Flow 2 highlight selection.

**Recommended:** `understanding/analysis_state.json` with `meta.operator_verified: true` so themes and audience match operator intent — same guard as Flow 1 extended analysis.

## Stage sequence

| Order | Stage key | Model tier | Output |
|-------|-----------|------------|--------|
| 1 | `podcast_show_description` | **flagship** | `flow_3_description/show_description.json` |
| 2 | `export_show_description` | — | `flow_3_description/show_description.md` (plain text export) |

Single LLM stage; export mirrors JSON → plain text on disk without a model call.

## Module

- `src/interview_mux/stages/publishing_flow3.py` — `podcast_show_description` + `export_show_description`
- `FLOW3_ORDER` in `pipeline.py`; `run_flow3` / `run_single_stage` branches
- CLI/GUI: `tools/run_flow.py --flow flow3`, `cli.flow_cmd`, `web/runner.py` (`mode: flow3`), `web/server.py` `FlowBody`, `web/stages.py` `FLOW3_STAGES`

## Context volley

Flow 3 uses a **rich `full` volley** — same pattern as flagship selection stages. Prior assistant turns should include:

- `content_context` — thesis, topics, claims, emotional beats
- `speaker_roles` — who is interviewer vs interviewee
- `segment_classification` — compact manifest slice with topic tags
- `missing_framing` / `optimal_questions` — only if gaps affect how the story should be framed (optional summaries)
- Operator profile slice — `themes`, `narrative`, `style`, `major_questions`, `entities`

See [context-padding.md](../../cross-cutting/context-padding.md) and [podcast-show-description.system.txt](../../prompts/publishing/podcast-show-description.system.txt).

## Operator checklist

| Check | Pass |
|-------|------|
| `show_description.json` | `word_count` 150–250; third person (spot-check hook + body) |
| Evidence | `evidence_segment_ids` non-empty; claims traceable to brief |
| Export | `show_description.md` readable; no markdown artifacts in plain export if undesired |

Full table: [operator-stage-checklists.md](../../workflows/operator-stage-checklists.md#flow-3--show-description).

## Related

- [pipeline.md](../../pipeline.md) — three flows overview
- [artifact-layout.md](../../cross-cutting/artifact-layout.md) — `flow_3_description/`
- [model-routing.md](../../cross-cutting/model-routing.md) — flagship for `podcast_show_description`

---

## Build-out

BUILD-045, BUILD-046, BUILD-080 · [README.md](../../build-out/README.md) · [steps-forward.md](../../build-out/steps-forward.md)
