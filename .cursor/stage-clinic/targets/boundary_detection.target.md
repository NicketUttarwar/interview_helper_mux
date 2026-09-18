# Target Spec — boundary_detection

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| Ideal-cuts bound + quality OK (`skip_boundary_llm_when_bound=true`, default) | Skip OpenAI; heal/mark done on existing `segments/boundaries.json`; optional edge-confidence fail-open | Fast unattended path |
| Ideal-cuts bound but coarse (`evaluate_boundary_quality.reject`) | Fall through to OpenAI segmentation | Completes with full-tape map |
| No bind / skip disabled | OpenAI ≤2 → persist → edge confidence fail-open → `_assert_boundary_quality` | Completes or honest StageError/quality refuse |
| Missing transcript / speakers / content_brief on LLM path | `read_json` hard fail — no hollow done | Honest halt |
| `ideal_cuts_materialized` missing on LLM path | Optional enrich only; LLM still runs if other hard reads OK | Completes (contract hard claim is overstated) |
| LLM schema/malformed | ≤2 then StageError | Honest halt |
| Post-LLM coarse/unsafe metrics | `_assert_boundary_quality` repair or raise (when `reject_coarse_fallback=true`) | Honest refuse / repair |
| Edge confidence throws | warn fail-open; stage may still done if quality OK | Continues |
| Partial vs Full-auto | Same skip/LLM rules — do not force always-LLM for Partial | `FULL_AUTO_REGRESSION_RISK` if always-LLM |

## Rules set (prefer deterministic)

- admit / skip when bind enabled + already-from-ideal-cuts + quality not reject
- admit / LLM when skip ineligible or coarse fallthrough
- refuse / missing transcript|speakers|brief on LLM path; refuse / StageError; refuse / quality assert fail
- wait_for_gate / never
- incomplete / missing primary `segments/boundaries.json`
- precise invalidate / live downstream only (drop retired `optimal_questions` claim)
- auto_resolve_default / keep `skip_boundary_llm_when_bound=true` + `reject_coarse_fallback=true`

## Complexity subtraction list

- Contract hard `ideal_cuts_materialized` while LLM `build_input` treats it optional — align claim to code
- Contract soft `transcript/full.json` while LLM hard-reads it — flip to hard
- Unused soft: review_queue / golden_facts / protected_zones (not in `build_input`)
- Stale invalidates `optimal_questions`
- Dual SSOT with materialize publisher — keep; do not remove quality gate before skip
- Do not remove skip path to “simplify” (regress Full-auto latency/`FULL_AUTO_REGRESSION_RISK`)

## Contract / dependency deltas (proposed; not applied)

- Hard: `transcript/full.json`, `understanding/speakers.json`, `understanding/content_brief.json`
- Soft: talking_points, ideal_cuts, ideal_cuts_materialized, SAP (as used)
- Drop unused soft probe/review paths
- Prune `optimal_questions` from invalidates
- Keep `volley_retry` (LLM path honest)

## Non-goals

- OpenAI segmentation creative quality
- Changing ideal-cuts bind_mode / materialize publisher policy (owned upstream)
- Local heavy ML
- Forcing always-LLM under Partial

## Acceptance checks

- Bound + quality OK → no OpenAI call; done + boundaries present
- Bound + coarse → LLM runs; log “too coarse”
- LLM path missing speakers/brief/transcript → fail before persist
- Quality reject after LLM → no silent done on unsafe map (`reject_coarse_fallback=true`)
- After BD-B1/B2: contract hard/soft matches `build_input` + skip preconditions

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| BD-B1 | P0 | unambiguous | Align contract hard/soft: transcript hard; demote `ideal_cuts_materialized` to soft (skip path still needs bind stamp via materialize) | dependency data + verify | 2 | no |
| BD-B2 | P1 | unambiguous | Prune unused soft inputs (review_queue, golden_facts, protected_zones) | dependency data | 2 | no |
| BD-B3 | P2 | unambiguous | Drop stale `optimal_questions` from invalidates | dependency data + ADG | 2,7 | no |
| BD-B4 | P1 | unambiguous | Preflight skip path: if `boundaries_already_from_ideal_cuts` but `segments/boundaries.json` missing/unreadable → fall through LLM or incompleteness (no crash mid-skip) | unit test bind-without-file | 1,2 | no |
| BD-B5 | P2 | confirmed | KEEP skip-when-bound default (5A) | defaults inventory | 1,5 | **yes** if force always-LLM |

## Defaults inventory impact

- Rows touched: Stage-local landmine — `analysis.ideal_cuts.skip_boundary_llm_when_bound=true`; `segmentation.reject_coarse_fallback=true`; coarse bind must fall through to LLM (do not stamp done on sparse keep-windows)

## target_status

`draft` — BD-B5 confirmed KEEP skip-when-bound (5A)
