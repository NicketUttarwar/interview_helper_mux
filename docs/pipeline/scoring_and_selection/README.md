# Scoring and selection

Branches after operator gate G2.

## Flow 1 (extended)

| Ticket | Output | Prompt |
|--------|--------|--------|
| BUILD-029 | `coverage_audit.json` | topic-coverage-audit |
| BUILD-030 | `narrative_plan.json` | narrative-arc-plan |
| BUILD-031 | `selection.json` | full-master-ranking |

**Goals:** Cover all interview topics; optimal podcast order (not chronological default).

**Before extended Flow 1:** Operator should verify interview profile (`meta.operator_verified`) — see [operator-gates.md](../../workflows/operator-gates.md).

**After ranking (planned):** `assembly_preview.wav` for listen-before-SFX — BUILD-069 in [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md).

**NLE (target BUILD-068):** GUI timeline edits in `segments/nle_edits.json` should affect `selection.json` / EDL on re-run.

## Flow 2

| Ticket | Output | Prompt |
|--------|--------|--------|
| BUILD-040 | `selection.json` | highlight-selection |

**Goals:** ≤5 non-overlapping, diverse, self-contained clips.

## Module

- `analysis_flow1_extended.py`
- `selection_flow1.py`
- `selection_flow2.py`
