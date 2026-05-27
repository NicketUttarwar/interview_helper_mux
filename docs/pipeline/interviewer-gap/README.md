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

| Path | Description |
|------|-------------|
| `understanding/gap_evaluations.json` | Per-segment framing check |
| `understanding/gap_report.json` | Aggregated fixes |
| `understanding/interviewer_script.txt` | Human-readable script |

## Operator gate

G1 — record lines into `vo_pickup/` when `delivery: record`

After each pickup (or when all lines are recorded), the operator should be **offered** optional [background noise removal](../audio_preclean/README.md) scoped to **`vo_pickup` only** — common when additional questions are recorded in a home office while the interview was cleaner. This does not force re-cleaning the original interview.

## Target assembly use (planned, BUILD-067)

Gap placements (`before` / `after` segment) and `vo_pickup` files must appear in Flow 1 `edl.json` and final mix — not only in JSON artifacts. See [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md).

## Prompts

- [missing-framing.system.txt](../../prompts/interviewer-gap/missing-framing.system.txt)
- [optimal-questions.system.txt](../../prompts/interviewer-gap/optimal-questions.system.txt)

## Models

| Stage | Tier (target) | Decompose |
|-------|----------------|-----------|
| `missing_framing` | flagship | yes |
| `optimal_questions` | flagship | no |

[llm-stage-model-matrix.md](../../cross-cutting/llm-stage-model-matrix.md)

## Module

`src/interview_mux/stages/gaps.py`

---

## Build-out

BUILD-025–027 · [README.md](../../build-out/README.md) · [steps-forward.md](../../build-out/steps-forward.md)
