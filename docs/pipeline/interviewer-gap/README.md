# Interviewer gap

Detect framing gaps and propose interviewer VO lines.

## Tickets

BUILD-026, BUILD-027

## Tools

**OpenAI** Chat Completions (`openai` SDK pin) — [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md); model IDs — [model-routing.md](../../cross-cutting/model-routing.md). Human mic for `delivery: record`.

## Inputs

| Path | Description |
|------|-------------|
| `segments/manifest.json` | All segments |
| `understanding/content_brief.json` | Context |

## Outputs

| Path | Validated on write | Description |
|------|-------------------|-------------|
| `understanding/gap_evaluations.json` | Yes | Per-segment framing check |
| `understanding/gap_report.json` | Yes | Framing lines (questions, summaries, prefaces, bridges) |
| `understanding/gap_framing_plan.json` | Yes | Succinct-master impact blocks |
| `understanding/interviewer_script.txt` | — | Human-readable script (not JSON schema) |

Gap-fill and flagship generation: [artifact-generation-and-validation.md](../../cross-cutting/artifact-generation-and-validation.md).

## Operator gates

- **G-Framing** (default No) — `POST …/gap-framing/enable`
- **G-Speaker / G-VoiceRef / G-Delivery** when framing enabled — see [chatterbox-interviewer-vo.md](../../cross-cutting/chatterbox-interviewer-vo.md)
- **G1** — record or Chatterbox-synthesize into `vo_pickup/` (optional skip)

After each pickup (or when all lines are recorded), the operator should be **offered** optional [background noise removal](../audio_preclean/README.md) scoped to **`vo_pickup` only** — common when additional questions are recorded in a home office while the interview was cleaner. This does not force re-cleaning the original interview.

## Assembly use (BUILD-067)

Gap placements (`before` / `after` segment) and `vo_pickup` paths appear in Flow 1 `edl.json` (`edl`). Final audible mix of VO + SFX is **BUILD-065/069** — see [assembly_and_mux](../assembly_and_mux/README.md).

## Prompts

- [missing-framing.system.txt](../../prompts/interviewer-gap/missing-framing.system.txt)
- [gap-framing-compose.system.txt](../../prompts/interviewer-gap/gap-framing-compose.system.txt)
- [optimal-questions.system.txt](../../prompts/interviewer-gap/optimal-questions.system.txt) (legacy alias)

## Models

| Stage | Tier (target) | Decompose |
|-------|----------------|-----------|
| `missing_framing` | flagship | yes |
| `gap_framing_compose` | flagship | no |

[llm-stage-model-matrix.md](../../cross-cutting/llm-stage-model-matrix.md)

## Module

`src/interview_mux/stages/gaps.py`
