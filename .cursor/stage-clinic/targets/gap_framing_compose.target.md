# Target Spec — gap_framing_compose

brain: 0.2.0 | target_status: draft | L3: B1+B3 applied; B2 confirmed allow empty (2B)

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| framing skipped | skip stub done | Continues |
| layup owns / freeze | no-op heal | Continues |
| LLM success | gap_report + companions | Completes |
| all shards fail | fill high gaps; incomplete if still hollow | Honest |
| empty lines after Yes | incomplete (Q2A CSP-05) | Blocks until lines or skip |

## Rules set

- admit / after evals+plan when framing on
- incomplete / hollow report / HG-2 family
- refuse / compose zero-line under Yes (CSP-05)

## Complexity subtraction

- Soft-success after empty shard merge without incompleteness check on small-batch path

## Acceptance checks

- Layup no-op; shard fail fill; hollow not done

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Ensure small-batch LLM fail path asserts completeness before done | pytest | 2,4 | no |
| B2 | P1 | confirmed | Zero-line after Yes: incomplete (Q2A CSP-05; reverses 2B) | `test_gfc_b2_zero_line_compose_incomplete_when_framing_yes` | 2,6 | med |
| B3 | P2 | unambiguous | Align sufficiency min_rows with skip stubs | contract | 7 | no |

## Defaults inventory impact

- G1 remains optional later — do not add stall here

## target_status

`draft` — B1+B3 applied; B2 Q2A CSP-05 zero-line under Yes → incomplete
