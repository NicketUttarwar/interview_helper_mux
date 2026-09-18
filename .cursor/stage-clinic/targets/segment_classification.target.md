# Target Spec — segment_classification

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| Ideal-cuts bound + `skip_classification_llm_when_bound=true` + non-empty det segments | Deterministic manifest write → force heal/done; speech sidecars fail-open | Fast unattended path (no OpenAI) |
| Det returns None / empty segments | Fall through to OpenAI | Completes via LLM |
| LLM single-shard (`required_ids` ≤ threshold) | `run_analysis_llm_stage` ≤2 → persist + stamp speakers | Completes |
| LLM multi-shard | Batches with `auto_complete=False`; merge; **all** required ids present or `RuntimeError`; then `heal_or_raise` | Honest refuse on incomplete batch |
| Missing boundaries / transcript / speakers (LLM payload) | `ValueError` from resolver — no hollow done | Honest halt |
| Soft `content_brief` missing | Allowed (optional in resolver) | Continues |
| Soft `master/edl.json` / review_queue / golden_facts / protected_zones | Unused by body | No behavior |
| Resplit unlinks `.stage_done` | Re-entry must re-classify honestly (no silent skip on stale) | Progression via heal; avoid thrash without batch honesty |
| Post LLM: specialists / topic bootstrap / ideal_cuts seed | Run after LLM path | Today **skipped on deterministic early-return** — see SC-B4 |
| Operator review gate | Must not add | `FULL_AUTO_REGRESSION_RISK` |

## Rules set (prefer deterministic)

- admit / deterministic when ideal-cuts bind + authority flags + non-empty segments
- admit / LLM otherwise when boundary contract ready
- refuse / resolver errors; refuse / StageError; refuse / batched missing segment ids
- wait_for_gate / never
- incomplete / empty or missing `segments/manifest.json` primary
- precise invalidate / live stages only (drop `optimal_questions`)
- auto_resolve_default / keep `skip_classification_llm_when_bound=true` + `deterministic_classification=true`

## Complexity subtraction list

- Contract soft `master/edl.json` and unused probe/review softs — prune
- Contract hard only `boundaries` while resolver requires transcript+speakers hard — align
- Deterministic early-return skipping topic bootstrap / selection-seed refresh — either share a post-pass or document intentional asymmetry
- Stale invalidates `optimal_questions`
- Do not add GUI classification review

## Contract / dependency deltas (proposed; not applied)

- Hard: `segments/boundaries.json`, `transcript/full.json`, `understanding/speakers.json`
- Soft: `content_brief`, talking_points (if used only on det path via authority), analysis_state
- Drop: `master/edl.json`, review_queue, golden_facts, protected_zones
- Prune `optimal_questions` from invalidates
- Keep `volley_retry` for LLM path

## Non-goals

- Classification label aesthetics / OpenAI quality
- Changing resplit coupling ownership (vernacular / topic resplit)
- Local heavy ML
- Always-LLM when bind is healthy (`FULL_AUTO_REGRESSION_RISK`)

## Acceptance checks

- Bound + det non-empty → no OpenAI; manifest segments ≥1; done
- Det empty/None → LLM path invoked
- Shard missing ids → RuntimeError; no done
- LLM path missing speakers/transcript → ValueError before persist
- After SC-B1: contract hard/soft matches `SEGMENTATION_INPUT_DEPS` + body
- Deterministic path either runs shared post-pass or documented skip with seed still valid

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| SC-B1 | P0 | unambiguous | Align contract hard inputs with `SEGMENTATION_INPUT_DEPS` (boundaries+transcript+speakers hard; brief soft) | dependency data + verify | 2 | no |
| SC-B2 | P1 | unambiguous | Prune unused softs (`master/edl.json`, review_queue, golden_facts, protected_zones) | dependency data | 2 | no |
| SC-B3 | P2 | unambiguous | Drop stale `optimal_questions` from invalidates | dependency data | 2,7 | no |
| SC-B4 | P1 | unambiguous | Deterministic early-return: also run topic_bootstrap + `refresh_selection_seed_from_boundaries` (and optionally specialists) like LLM path | unit test det path post-hooks | 1,2,7 | no |
| SC-B5 | P2 | confirmed | KEEP skip-classification-when-bound (5A) | defaults inventory | 1,5 | **yes** if force always-LLM |
| SC-B6 | P2 | needs_you | Resplit↔classification thrash: harden batch re-entry caps vs leave to thrash_hardening? | thrash_hardening + resplit unlink tests | 1,7 | no if caps only |

## Defaults inventory impact

- Rows touched: Stage-local landmine — `analysis.ideal_cuts.skip_classification_llm_when_bound=true`; `talking_points_authority.deterministic_classification=true`; shard thresholds via `classification_context_cfg`; resplit can unlink done → re-entry

## target_status

`draft` — SC-B5 confirmed KEEP skip-when-bound (5A); SC-B6 still open

