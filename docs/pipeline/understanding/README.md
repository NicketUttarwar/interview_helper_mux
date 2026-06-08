# Understanding

Speaker roles, content brief, **per-interview analysis profile**, and source-derived acoustic pacing/mix profile — [source-derived-sonic-mix-profile.md](../../cross-cutting/source-derived-sonic-mix-profile.md).

## Tickets

BUILD-022, BUILD-023, BUILD-082

## Tools

**OpenAI** Chat Completions (envelope + memory padding) — **flagship** tier for `speaker_roles`, `content_context`, and `content_brief_reanchor` — [model-routing.md](../../cross-cutting/model-routing.md) · [artifact-generation-and-validation.md](../../cross-cutting/artifact-generation-and-validation.md)

## Inputs

| Path | Description |
|------|-------------|
| `transcript/full.json` | Full transcript |
| `transcript/speakers.json` | Diarization labels |
| `ingest/normalized.wav` | Normalized audio for `source_acoustic_profile` derivation |
| `understanding/analysis_state.json` | Rolling memory (created at first LLM stage) |

## Outputs

| Path | Editable | Description |
|------|----------|-------------|
| `understanding/analysis_state.json` | **Yes** | Themes, major questions, style, narrative, completion |
| `understanding/investigation_queue.json` | Yes | Open investigations |
| `understanding/speakers.json` | Yes | Role mapping |
| `understanding/content_brief.json` | Yes | Thesis, topics, typed claims, `topic_relationships`, emotional beats — two-pass (`content_context` then `content_brief_reanchor`) |
| `understanding/source_acoustic_profile.json` | Yes | WPM, pause stats, mix contract — derived once after transcription + review prep |

| `understanding/value_features.json` | Optional | Transcript/audio metrics when value-analysis flags on |

## Operator workflow

1. Run analysis stages (or full `run_analysis.py`)
2. In **Stage outputs**, confirm `content_brief.json` is **complete** after `content_context` (semantic brief) and again after `content_brief_reanchor` (timeline anchors + topic links)
3. Open **Interview profile** in the GUI — review themes, major questions, style
4. Edit JSON in **Files** tab if needed (Zod + server validation on save)
5. Click **Mark profile verified** when the profile is correct
6. Use **Fill gaps** on partial artifacts or **Redo from selected stage** to refresh LLM output

See [analysis-memory.md](../../cross-cutting/analysis-memory.md) and [artifact-generation-and-validation.md](../../cross-cutting/artifact-generation-and-validation.md).

## Prompts

- [analysis-preamble.system.txt](../../prompts/_shared/analysis-preamble.system.txt) (prepended to all LLM stages)
- [speaker-roles.system.txt](../../prompts/understanding/speaker-roles.system.txt)
- [content-context.system.txt](../../prompts/understanding/content-context.system.txt)
- [content-brief-reanchor.system.txt](../../prompts/understanding/content-brief-reanchor.system.txt)

## Models

| Stage | Tier (default) | Decompose | On-disk artifact |
|-------|----------------|-----------|------------------|
| `speaker_roles` | flagship | no | `understanding/speakers.json` (stratified `transcript_samples` from opening/middle/closing) |
| `content_context` | flagship | yes | `understanding/content_brief.json` (+ `memory_updates` → `analysis_state.json`) |
| `content_brief_reanchor` | flagship | yes | `understanding/content_brief.json` (patch segment_ids, relationships) |

Gap-fill: each stage input includes `gap_fill_context` when a prior partial file exists.

[llm-stage-model-matrix.md](../../cross-cutting/llm-stage-model-matrix.md) · [model-routing.md](../../cross-cutting/model-routing.md)

## Module

`src/interview_mux/stages/understanding.py`, `analysis_memory.py`, `analysis_orchestrator.py`, `artifact_completeness.py`, `artifact_writes.py`

---

## Build-out

BUILD-022–023, BUILD-018 · [README.md](../../build-out/README.md) · [steps-forward.md](../../build-out/steps-forward.md)
