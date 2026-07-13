# Single-flow rename map

Canonical renames applied during the single-flow simplification migration (analysis → delivery podcast master).

## Pipeline

| Legacy | Canonical |
|--------|-----------|
| `DELIVERY_ORDER` | `DELIVERY_ORDER` |
| `REMOVED_FLOW2_ORDER` | *(deleted)* |
| `REMOVED_FLOW3_ORDER` | *(deleted)* |
| `run_delivery` | `run_delivery` |
| `REMOVED_run_flow2` | *(deleted)* |
| `REMOVED_run_flow3` | *(deleted)* |
| `_delivery_stage_fns` | `_delivery_stage_fns` |

## Gates

| Legacy | Canonical |
|--------|-----------|
| `require_delivery_gates` | `require_delivery_gates` |
| `require_profile_verified_for_delivery` | `require_profile_verified_for_delivery` |
| `assert_delivery_ready` | `assert_delivery_ready` |
| `build_delivery_readiness_report` | `build_delivery_readiness_report` |
| `P0_DELIVERY_SPINE` | `P0_DELIVERY_SPINE` |
| `set_REMOVED_selected_flow` | *(deleted — no G2)* |
| `get_REMOVED_selected_flow` | *(deleted)* |
| `require_REMOVED_selected_flow_flow1/2` | *(deleted)* |
| `REMOVED_selected_flow`, `REMOVED_flow_intent`, `REMOVED_g2_flow_select` | *(removed from run_meta / GUI)* |

## Stage IDs

| Legacy | Canonical |
|--------|-----------|
| `sound_design_plan` | `sound_design_plan` |
| `edl` | `edl` |
| `mmaudio_sfx` | `mmaudio_sfx` |
| `mix` | `mix` |
| `master_finalize` | `master_finalize` |
| Flow 2 / Flow 3 stages | *(deleted)* |
| *(new)* `delivery_brief_build` | Adaptive soft targets after `optimal_questions` → `understanding/delivery_brief.json` |
| `post_sound_plan_flow1` checkpoint | `post_sound_plan` |

## Artifact paths

| Legacy | Canonical |
|--------|-----------|
| `master/` | `master/` |
| `REMOVED_flow2/` | *(deleted)* |
| `show_notes/` | *(deleted — show notes QC module only)* |

## Stage modules (git mv)

| Legacy | Canonical |
|--------|-----------|
| `stages/analysis_extended.py` | `stages/analysis_extended.py` |
| `stages/selection.py` | `stages/selection.py` |
| `stages/assembly.py` | `stages/assembly.py` |
| `stages/REMOVED_selection_flow2.py` | *(deleted)* |
| `stages/REMOVED_assembly_flow2.py` | *(deleted)* |
| `stages/REMOVED_publishing_flow3.py` | *(deleted)* |

## Config / plans

| Legacy | Canonical |
|--------|-----------|
| `flow_plans.podcast` | `flow_plans.podcast` |
| `REMOVED_flow_plans_flow2` | *(deleted)* |
| `show_notes_qc` | `show_notes_qc` |

## CLI / tools

| Legacy | Canonical |
|--------|-----------|
| `tools/run_delivery.py` | `tools/run_delivery.py` |
| `--flow flow1` | delivery run (no flow picker) |

## Backward-compat aliases (temporary)

- `DELIVERY_ORDER = DELIVERY_ORDER`
- `run_delivery = run_delivery`

These aliases may remain until downstream tests and docs are fully updated.
