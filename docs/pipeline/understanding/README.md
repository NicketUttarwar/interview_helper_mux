# Understanding

Speaker roles, content brief, and **per-interview analysis profile** from transcript.

## Tickets

BUILD-022, BUILD-023

## Tools

OpenAI Chat Completions (envelope + memory padding)

## Inputs

| Path | Description |
|------|-------------|
| `transcript/full.json` | Full transcript |
| `transcript/speakers.json` | Diarization labels |
| `understanding/analysis_state.json` | Rolling memory (created at first LLM stage) |

## Outputs

| Path | Editable | Description |
|------|----------|-------------|
| `understanding/analysis_state.json` | **Yes** | Themes, major questions, style, narrative, completion |
| `understanding/investigation_queue.json` | Yes | Open investigations |
| `understanding/speakers.json` | Yes | Role mapping |
| `understanding/content_brief.json` | Yes | Thesis, topics, claims, beats |

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

`speaker_roles`, `content_context` — see [model-routing.md](../../cross-cutting/model-routing.md)

## Module

`src/interview_mux/stages/understanding.py`, `analysis_memory.py`, `analysis_orchestrator.py`
