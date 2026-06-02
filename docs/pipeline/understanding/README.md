# Understanding

Speaker roles, content brief, **per-interview analysis profile**, and source-derived acoustic pacing/mix profile — [source-derived-sonic-mix-profile.md](../../cross-cutting/source-derived-sonic-mix-profile.md).

## Tickets

BUILD-022, BUILD-023, BUILD-082

## Tools

**OpenAI** Chat Completions (envelope + memory padding) — [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md) · [model-routing.md](../../cross-cutting/model-routing.md)

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
| `understanding/content_brief.json` | Yes | Thesis, topics, claims, beats |
| `understanding/source_acoustic_profile.json` | Yes | WPM, pause stats, mix contract — derived once after transcription + review prep |

| `understanding/value_features.json` | Optional | Transcript/audio metrics when value-analysis flags on |

## Operator workflow

1. Run analysis stages (or full `run_analysis.py`)
2. Open **Interview profile** in the GUI — review themes, major questions, style
3. Edit JSON directly if preferred; click **Mark profile verified**
4. Redo from a stage if LLM output should reflect your edits

See [analysis-memory.md](../../cross-cutting/analysis-memory.md).

## Prompts

- [analysis-preamble.system.txt](../../prompts/_shared/analysis-preamble.system.txt) (prepended to all LLM stages)
- [speaker-roles.system.txt](../../prompts/understanding/speaker-roles.system.txt)
- [content-context.system.txt](../../prompts/understanding/content-context.system.txt)

## Models

| Stage | Tier (target) | Decompose |
|-------|----------------|-----------|
| `speaker_roles` | economy | no |
| `content_context` | economy | yes |

[llm-stage-model-matrix.md](../../cross-cutting/llm-stage-model-matrix.md) · [model-routing.md](../../cross-cutting/model-routing.md)

## Module

`src/interview_mux/stages/understanding.py`, `analysis_memory.py`, `analysis_orchestrator.py`

---

## Build-out

BUILD-022–023, BUILD-018 · [README.md](../../build-out/README.md) · [steps-forward.md](../../build-out/steps-forward.md)
