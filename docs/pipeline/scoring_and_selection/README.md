# Scoring and selection

**LLM stack:** [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md) · [model-routing.md](../../cross-cutting/model-routing.md)

Branches after operator gate G2.

## Flow 1 (extended)

| Ticket | Output | Prompt |
|--------|--------|--------|
| BUILD-029 | `coverage_audit.json` | topic-coverage-audit |
| BUILD-030 | `narrative_plan.json` | narrative-arc-plan |
| BUILD-031 | `selection.json` | full-master-ranking |

**Goals:** Cover all interview topics; optimal podcast order (not chronological default).

**Before extended Flow 1:** Operator should verify interview profile (`meta.operator_verified`) — see [operator-gates.md](../../workflows/operator-gates.md).

**After ranking:** `assembly_preview.wav` for listen-before-SFX — see [stage-registry.md](../../build-out/stage-registry.md) · [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md).

**Narrative QC:** `python tools/validate_narrative.py --run-id <exec_id>` — topic coverage + non-empty chapters (`interview_mux/narrative_qc.py`). Pipeline warns before `full_master_ranking` / `edl_flow1`; `narrative_qc.strict: true` blocks.

**Extended EDL narrative QC:** `edl_narrative_audit` runs after `sound_design_vo_finalize` with local LLM volley framing and flagship model review. `edl_flow1` then runs deterministic final-EDL checks (`interview_mux/edl_narrative_qc.py`) for selection parity, coverage survival, chapter continuity, ordering constraints, transition anchors, and gap placements. CLI: `python tools/validate_narrative.py --run-id <exec_id> --include-edl`.

**NLE (BUILD-068):** GUI timeline edits in `segments/nle_edits.json` affect `selection.json` on `full_master_ranking` and `edl_flow1` re-run.

## Flow 2

| Ticket | Output | Prompt |
|--------|--------|--------|
| BUILD-040 | `selection.json` | highlight-selection |

**Goals:** ≤5 non-overlapping, diverse, self-contained clips.

## Models

| Stage | Tier (target) | Decompose |
|-------|----------------|-----------|
| `topic_coverage_audit` | flagship | yes |
| `narrative_arc_plan` | flagship | no |
| `full_master_ranking` | flagship | yes |
| `highlight_selection` | flagship | yes |
| `podcast_show_description` | flagship | no |

## Flow 3 (publishing)

| Ticket | Output | Prompt |
|--------|--------|--------|
| BUILD-045 | `show_description.json` | podcast-show-description |
| BUILD-046 | `show_description.md` | — (export) |

**Goals:** ~200-word third-person blurb; rich context volley; flagship model. No selection or mux.

See [publishing/README.md](../publishing/README.md).

## Module

- `analysis_flow1_extended.py`
- `selection_flow1.py`
- `selection_flow2.py`
- `publishing_flow3.py`

---

## Build-out

BUILD-029–031, BUILD-040, BUILD-045 · [README.md](../../build-out/README.md) · [repository-map.md](../../build-out/repository-map.md)
