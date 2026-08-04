# Scoring and selection

**LLM stack:** [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md) · [model-routing.md](../../cross-cutting/model-routing.md) · validated artifact writes — [artifact-generation-and-validation.md](../../cross-cutting/artifact-generation-and-validation.md)

Single delivery path after analysis (Flow 2 highlight selection and G2 were **removed** — [v2/drop-manifest.md](../../v2/drop-manifest.md)).

## Full master (live)

| Ticket | Output | Prompt |
|--------|--------|--------|
| BUILD-029 | `coverage_audit.json` | topic-coverage-audit |
| BUILD-030 | `narrative_plan.json` | narrative-arc-plan |
| BUILD-031 | `selection.json` | full-master-ranking |

**Goals:** Cover all interview topics; optimal podcast order (not chronological default). Followed by [Refinement Pass](../../cross-cutting/refinement-passes.md).

**After ranking:** `assembly_preview.wav` for listen-before-SFX — see [stage-contracts/00-INDEX.md](../../cross-cutting/stage-contracts/00-INDEX.md) · [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md).

**Narrative QC:** `python tools/validate_narrative.py --run-id <exec_id>` — topic coverage + non-empty chapters (`interview_mux/narrative_qc.py`). Pipeline warns before `full_master_ranking` / `edl`; `narrative_qc.strict: true` blocks.

**Extended EDL narrative QC:** `edl_narrative_audit` runs after `sound_design_vo_finalize` with local LLM volley framing and flagship model review. `edl` then runs deterministic final-EDL checks (`interview_mux/edl_narrative_qc.py`). CLI: `python tools/validate_narrative.py --run-id <exec_id> --include-edl`.

**NLE (BUILD-068):** GUI timeline edits in `segments/nle_edits.json` affect `selection.json` on `full_master_ranking` and `edl` re-run.

## Models

| Stage | Tier (target) | Decompose |
|-------|----------------|-----------|
| `topic_coverage_audit` | flagship | yes |
| `narrative_arc_plan` | flagship | no |
| `full_master_ranking` | flagship | yes |
| `transitions` | economy / mid | no |

## Heritage (removed)

Flow 2 highlight selection (`REMOVED_highlight_selection`, `REMOVED_selection_flow2.py`) and Flow 3 publishing stages are deleted. Do not reintroduce G2.
