# Target Spec — sound_design_plan

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| enabled+LLM ok | fingerprint SDP delivery producer | Completes |
| LLM fail | refuse | Honest |
| enabled=false | skip heal without starving later? | needs_you |
| palettes-only file | not seed_complete | Honest |

## Rules set

- admit / producer_stage==sound_design_plan
- refuse / LLM|unsanitary
- incomplete / invent unpaid

## Complexity subtraction

- Keep compose_deferred cues; music_palette owns real cues

## Non-goals

- Wave 1 patches

## Acceptance checks

- fingerprint; assets≥1; skip path honesty

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Keep producer fingerprint gate | agenda tests | 2,5 | yes |
| B2 | P1 | unambiguous | Fix contract consumers list | yaml | 7 | no |
| B3 | P1 | needs_you | enabled=false Full-auto policy | intent | 5 | yes |

## Defaults inventory impact

- `sound_design.enabled=true` landmine if false

## target_status

`draft`
