# Target Spec — content_brief_reanchor

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| hard manifest + prior `content_brief` + speakers readable | OpenAI reanchor ≤2 → persist; status must be `complete` → done | Completes unattended |
| soft boundaries present | Compact id/timeline rows attached | Enrichment only |
| soft boundaries missing | LLM still runs | Completes |
| speakers missing | `read_json` hard fail (body) — no hollow done | Honest halt |
| prior brief hollow / incomplete after persist | `RuntimeError` (“must persist a complete brief”) — no done | Honest halt (`FULL_AUTO_REGRESSION_RISK` if softened) |
| OpenAI schema/malformed | ≤2 then StageError | Honest halt |
| Topic bootstrap pre-hook throws/patches | Fail-open log; continue to LLM | Continues |
| Post-done coherence analysis | Optional `maybe_run_coherence_analysis` | Soft post-hook |
| Resplit unlinks done | Re-entry reanchors honestly | Progression; avoid incomplete overwrite thrash |

## Rules set (prefer deterministic)

- admit / when manifest + prior brief + speakers readable
- refuse / missing those reads; refuse / persist status ≠ complete; refuse / StageError after ≤2
- wait_for_gate / never
- incomplete / never mark_done on incomplete brief status
- precise invalidate / live downstream only (drop `optimal_questions`)
- auto_resolve_default / N/A — keep thesis/topics sufficiency blocking

## Complexity subtraction list

- Contract soft `speakers.json` while body hard-reads it — align to hard
- Stale invalidates `optimal_questions`
- Shared SSOT with `content_context` on same path — keep dual producer (intentional reanchor); do not split to a second file without campaign intent
- Do not soften completeness gate for Partial convenience

## Contract / dependency deltas (proposed; not applied)

- Hard: `segments/manifest.json`, `understanding/content_brief.json`, `understanding/speakers.json`
- Soft: `segments/boundaries.json` only
- Prune `optimal_questions` from invalidates
- Keep `volley_retry` (LLM stage)

## Non-goals

- Brief prose quality / thesis creativity
- Splitting reanchor output to a new artifact path
- Local heavy ML
- Operator approval of reanchored brief

## Acceptance checks

- Missing speakers/manifest/brief → fail before done
- Persist with incomplete status → RuntimeError; no `.stage_done`
- Schema fail ×2 → StageError
- Successful path: thesis/topics sufficiency pass; ownership allows dual producer with content_context
- After CBR-B1: contract hard list includes speakers

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| CBR-B1 | P0 | unambiguous | Promote `understanding/speakers.json` to hard contract input (matches `build_input`) | dependency data + verify | 2 | no |
| CBR-B2 | P2 | unambiguous | Drop stale `optimal_questions` from invalidates | dependency data | 2,7 | no |
| CBR-B3 | P1 | unambiguous | Keep completeness RuntimeError; add focused test that hollow persist cannot mark_done | test_content_brief_reanchor | 2,4 | **yes** if gate softened |
| CBR-B4 | P2 | needs_you | Resplit↔reanchor oscillation: rely on thrash_hardening vs stage-local cap? | thrash_hardening + unlink tests | 1,7 | no if caps only |

## Defaults inventory impact

- Rows touched: Stage-local landmine — completeness gate on shared `content_brief.json` SSOT; resplit can unlink done → re-entry; do not soften thesis/topics sufficiency

## target_status

`draft`
