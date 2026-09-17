# Target Spec — edl_narrative_audit

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| vo heard + LLM pass | audit pass; edl free | Completes |
| vo not heard | incomplete → vo_synthesize | Honest HE-1 |
| verdict fail | block edl; remutate bounded | Honest |
| LLM exhaust | refuse | Honest |

## Rules set

- admit / pass verdict
- refuse / LLM
- incomplete / heard_wav|fail verdict
- precise invalidate / prefer edl not vo_synthesize unless bind bad

## Complexity subtraction

- Bound remutate; keep HE-1

## Contract / dependency deltas (proposed)

- hard += vo completeness signal; fix consumers

## Non-goals

- Wave 1 patches

## Acceptance checks

- HE-1; edl blocks on fail

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Keep HE-1 heard_wav | tests | 2,6 | yes |
| B2 | P1 | unambiguous | Fix contract hard/consumers | yaml | 2,7 | no |
| B3 | P1 | needs_you | invalidates vo_synthesize vs thrash | intent | 1,7 | yes |

## Defaults inventory impact

- narrative remutate thrash landmine

## target_status

`draft`
