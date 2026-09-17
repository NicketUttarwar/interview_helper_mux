# Target Spec — ideal_cuts_propose

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| `analysis.ideal_cuts.enable=true` (default) + talking_points + transcript | OpenAI propose ≤2 attempts → persist → mark_done | Completes unattended |
| talking_points missing | `RuntimeError` before LLM — no hollow done | Honest halt / heal pin talking_points |
| OpenAI schema/malformed | ≤2 then `StageError` — no soft-lie done | Honest halt |
| long tape (≥15 min) cuts clustered early | redistribute once; if still `< min_span_coverage_ratio` (0.45) → RuntimeError; retryable once as schema-like | Honest refuse after budget; no hollow early-cluster master seed |
| short tape (&lt;15 min) | span floor not enforced | Completes |
| `enable=false` | placeholder single cut + `heal_or_refuse_mark(..., force=True)` | Completes with stub — **downstream bind/skip paths must tolerate**; do not change default enable |
| soft brief/speakers present | attached to LLM packet when present | Optional enrichment |
| soft review_queue / golden_facts / protected_zones | **unused by `build_input` today** | No behavior change until contract pruned |

## Rules set (prefer deterministic)

- admit / when enable + talking_points + transcript readable
- refuse / missing talking_points; refuse / StageError after ≤2; refuse / span floor after redistribute+retry
- wait_for_gate / never
- incomplete / missing primary `understanding/ideal_cuts.json` (generic artifact incompleteness)
- precise invalidate / none declared (materialize consumes fresh propose)
- auto_resolve_default / N/A — keep `enable=true` default; never lower span floor for Partial-only

## Complexity subtraction list

- Contract soft inputs never read: `transcript/review_queue.json`, `analysis/run_golden_facts.json`, `transcript/protected_zones.json`
- Disabled stub force-done as a second product path — prefer single enabled path for Full-auto; leave disable as explicit operator/dev escape (document, don’t invent Partial-only stub)
- Host redistribute + LLM retry double complexity — keep (load-bearing honesty); do not remove span gate

## Contract / dependency deltas (proposed; not applied)

- Keep hard transcript + talking_points; keep soft brief + speakers (actually used)
- Drop unused soft probe/review paths from this stage’s contract inputs
- Keep `volley_retry` + `full_stage_rerun` (LLM stage — remediation claim matches)
- Optionally surface `min_span_coverage_ratio` in `app.defaults.json` to match code default 0.45 (docs honesty only)

## Non-goals

- Prompt creative quality / cut aesthetics
- Changing 15 min span gate threshold or 0.45 floor for Partial convenience (`FULL_AUTO_REGRESSION_RISK`)
- Local heavy ML
- Materialize / boundary bind_mode policy (owned by `ideal_cuts_materialize`)

## Acceptance checks

- Missing talking_points → no LLM call, no done
- Schema fail ×2 → StageError, no done
- ≥15 min clustered cuts → redistribute log; still under floor → RuntimeError; one LLM retry then hard stop
- `enable=true` default path writes schema-valid cuts with min_rows≥1
- `enable=false` writes placeholder + done (document as intentional skip stub)
- After ICP-B1: contract soft list matches `build_input` reads only

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| ICP-B1 | P1 | unambiguous | Prune unused soft inputs (review_queue, golden_facts, protected_zones) from contract | dependency data + verify | 2 | no |
| ICP-B2 | P2 | unambiguous | Document/code-default align: put `min_span_coverage_ratio: 0.45` in `app.defaults.json` ideal_cuts block | defaults audit | 2,5 | no |
| ICP-B3 | P2 | needs_you | `enable=false` stub force-done: keep as escape hatch vs incompleteness refuse? | disable-path pytest + materialize skip | 2 | **yes** if default enable flipped or stub removed without materialize skip |
| ICP-B4 | P3 | unambiguous | Ensure span persist RuntimeError always raises StageError after attempt 2 (no fail-open for ideal_cuts) | llm_simple path + focused test | 2,4 | no |

## Defaults inventory impact

- Rows touched: Stage-local landmine — `analysis.ideal_cuts.enable` default **true**; `min_span_coverage_ratio` code default **0.45** (long tapes ≥15 min); do not lower floor for Partial-only

## target_status

`draft`
