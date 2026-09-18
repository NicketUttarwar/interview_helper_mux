# Target Spec — air_script_seams

brain: 0.2.0 | target_status: applied

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| enable=true clean | Pass B + heal | Completes |
| VO contract drift | restore + refuse (no swallow) | Honest fail |
| enable=false | skip with honest done/skip policy | No hollow seed |
| soft freeze | no-op plan + heal (KEEP) | Continues |

## Rules set

- admit / heal after clear drift
- refuse / contract drift
- incomplete / stamped drift sidecar
- ASS-B3 KEEP: cautious soft-freeze no-op (no forced reseat)

## Complexity subtraction

- Keep deterministic; fix contract tier claim

## Contract / dependency deltas (proposed)

- tier → process/deterministic; confirm gap_framing_plan write

## Non-goals

- Wave 1 patches
- Soft-freeze reseat (operator KEEP)

## Acceptance checks

- Drift restore; enable-off honesty; soft-freeze no-op retained

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Contract tier vs non-LLM body | contract | 2,7 | no |
| B2 | P0 | unambiguous | enable=false mark/skip honesty | stage_completion | 2,5 | yes |
| B3 | P1 | unambiguous | KEEP soft-freeze no-op (notes) | seat_authority | 1 | yes |

## Defaults inventory impact

- `mastering.air_script.enable=true` landmine if flipped
- ASS-B3 KEEP: soft-freeze no product change

## Wave 2 apply log

- B1 + B2 applied (CONTINUE CSP-01)
- B3 KEEP (1B): notes only — cautious soft-freeze no-op; ASC-B3 does not force reseat

## target_status

`applied`
