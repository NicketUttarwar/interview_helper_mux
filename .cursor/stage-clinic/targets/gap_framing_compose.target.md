# Target Spec — gap_framing_compose

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| framing skipped | skip stub done | Continues |
| layup owns / freeze | no-op heal | Continues |
| LLM success | gap_report + companions | Completes |
| all shards fail | fill high gaps; incomplete if still hollow | Honest |
| empty lines after Yes | incomplete preferred over hollow done | Honest |

## Rules set

- admit / after evals+plan when framing on
- incomplete / hollow report / HG-2 family
- refuse / soft-done empty when framing Yes

## Complexity subtraction

- Soft-success after empty shard merge without incompleteness check on small-batch path

## Acceptance checks

- Layup no-op; shard fail fill; hollow not done

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Ensure small-batch LLM fail path asserts completeness before done | pytest | 2,4 | no |
| B2 | P1 | needs_you | Zero-line after Yes: incomplete vs allow | intent | 2,6 | yes |
| B3 | P2 | unambiguous | Align sufficiency min_rows with skip stubs | contract | 7 | no |

## Defaults inventory impact

- G1 remains optional later — do not add stall here

## target_status

`draft`
