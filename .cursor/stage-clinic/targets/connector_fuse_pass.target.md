# Target Spec — connector_fuse_pass

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| `enabled=true` (default) + manifest present | Seam enumerate → economy LLM (±det fallback) → apply until fixed_point or finite round/fuse caps → audit + heal | Completes unattended |
| `enabled=false` | `persist_fuse_skip(disabled)` + heal/done (HS-3 audit stub for analysis pass) | Completes (skip path) |
| missing manifest | `persist_fuse_skip(missing_manifest)` + heal | Completes honest skip |
| OpenAI seam fail | `deterministic_fallback_on_llm_fail=true` → det verdicts; continue | Completes without hard stall |
| empty packets / settled seams | `fixed_point=true`; heal | Completes |
| `max_fuses_per_pass`/`max_fuse_rounds` = 0 in defaults | Treat as finite caps (24 / 8), **not** unlimited | Caps thrash (DEEP-FUSE-01) |
| Oscillation / locked seams | Caps + locked-seam pins (HS-4) | No infinite rewrite loop |
| Contract hard `low_conf_islands` missing | Body still runs (islands soft/enrichment) | Completes — contract overstates hard |
| Operator seam approval | Must not add | `FULL_AUTO_REGRESSION_RISK` |
| `pass_id=pre_ranking` / `junction_heal` | Same fuse core; different writer/heal stage; junction may reopen-gate | Out of this stage’s seed body but shared code |

## Rules set (prefer deterministic)

- admit / skip when disabled or missing manifest (honest skip stub + heal)
- admit / fuse when enabled + manifesto present; prefer incomplete_thought_only hints
- refuse / only when fail-closed paths explicitly raise (prefer fallback over hollow)
- wait_for_gate / never on analysis `post_sanitize` pass
- incomplete / missing HS-3 audit for analysis writer (`analysis/connector_fuse_audit.json`)
- precise invalidate / keep live consumers; verify profiles match long invalidates list
- auto_resolve_default / keep enabled=true, incomplete_thought_only=true, deterministic_fallback=true, finite 0→24/8 caps

## Complexity subtraction list

- Contract tier `process` while OpenAI economy seams run — retier to llm/hybrid claim
- Contract hard `low_conf_islands` — demote soft (body gates on manifest/enabled)
- Soft `manifest` is effectively required for work path — promote hard **or** keep soft with skip stub (current)
- Wrapper logs “skipped enabled=false” then still calls `fuse_pass` (benign; inner skips) — optional tidy
- Multi-round OpenAI control — keep caps; do not remove fixed_point / locked seams
- Do not add GUI seam approval

## Contract / dependency deltas (proposed; not applied)

- Tier: reflect OpenAI seam adjudicate (`llm_full` or documented hybrid process+economy)
- Hard: `segments/manifest.json` (or keep soft + skip — prefer hard for honesty of “work” path)
- Soft: `analysis/low_conf_islands.json`, must_keep, transcript
- Keep remediation `volley_retry` (seams are LLM) + `full_stage_rerun`
- Outputs: audit primary for analysis pass; document pre_ranking rounds primary separately

## Non-goals

- Seam prompt creative quality
- Changing junction_heal reopen policy (timeline gate)
- Local heavy ML
- Unlimited rounds/fuses via defaults `0` meaning infinity

## Acceptance checks

- Disabled → audit/rounds skip_reason=disabled; stage done; incompleteness None
- Missing manifest → skip_reason=missing_manifest; done
- Enabled happy path → audit exists; heal marks fuse_writer_stage done
- LLM fail → fallback verdicts when configured; no bare hollow done without audit
- Defaults 0 caps → finite 24/8 applied (not 10k)
- Oscillation tests (HS-4) still pin
- After CFP-B1: contract tier/inputs match body

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| CFP-B1 | P0 | unambiguous | Align contract: demote `low_conf_islands` to soft; promote or document manifest as work-path prerequisite | dependency data + verify | 2 | no |
| CFP-B2 | P1 | unambiguous | Retier contract from `process` to reflect OpenAI economy seams (or hybrid annotation) | dependency data / StageInfo | 2,4 | no |
| CFP-B3 | P1 | unambiguous | Keep finite interpretation of defaults `0` for max_fuses/rounds; document in defaults inventory (already coded) | test DEEP-FUSE / unit for 0→24/8 | 1,3,5 | **yes** if 0 becomes unlimited again |
| CFP-B4 | P2 | unambiguous | Tidy wrapper: early-return after disabled log **or** stop double-messaging (inner skip is SSOT) | low_conf_fuse_stages.py | 2 | no |
| CFP-B5 | P2 | needs_you | Keep `incomplete_thought_only=true` + no operator seam approval? (recommend keep) | defaults inventory | 3,5 | **yes** if require human seam OK |
| CFP-B6 | P2 | needs_you | Invalidates fan-out to delivery: trim vs keep for safety? | ADG + execution profiles | 7 | yes if over-clear thrash |

## Defaults inventory impact

- Rows touched: Stage-local landmine — `analysis.connector_fuse.enabled=true`; `incomplete_thought_only=true`; `deterministic_fallback_on_llm_fail=true`; `max_fuses_per_pass=0`/`max_fuse_rounds=0` mean finite 24/8 in code; thrash hotspot with pre_ranking + junction_heal siblings

## target_status

`draft` — Wave 2 applied CFP-B1–B4; CFP-B5/B6 still `needs_you`
