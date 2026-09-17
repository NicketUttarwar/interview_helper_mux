# Target Spec — air_script_seams

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| enable=true clean | Pass B + heal | Completes |
| VO contract drift | restore + refuse (no swallow) | Honest fail |
| enable=false | skip with honest done/skip policy | No hollow seed |
| soft freeze | no-op plan + heal | Continues |

## Rules set

- admit / heal after clear drift
- refuse / contract drift
- incomplete / stamped drift sidecar

## Complexity subtraction

- Keep deterministic; fix contract tier claim

## Contract / dependency deltas (proposed)

- tier → process/deterministic; confirm gap_framing_plan write

## Non-goals

- Wave 1 patches

## Acceptance checks

- Drift restore; enable-off honesty

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Contract tier vs non-LLM body | contract | 2,7 | no |
| B2 | P0 | unambiguous | enable=false mark/skip honesty | stage_completion | 2,5 | yes |
| B3 | P1 | needs_you | soft-freeze no-op vs required reseat | intent | 1 | yes |

## Defaults inventory impact

- `mastering.air_script.enable=true` landmine if flipped

## target_status

`draft`
