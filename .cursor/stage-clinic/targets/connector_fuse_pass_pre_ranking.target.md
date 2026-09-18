# Target Spec — connector_fuse_pass_pre_ranking

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| enabled + manifest | Fuse to fixed point; pass_id=pre_ranking | Completes |
| disabled / missing manifest | skip rounds + heal | Completes |
| oscillation | Cap / pin; no infinite | Honest |

## Rules set

- same as fuse_pass + pass_id stamp
- heal via fuse_writer_stage(pre_ranking)
- skip writes rounds artifact

## Complexity subtraction

- Shared fuse body; no second implementation

## Acceptance checks

- HS-3 writer; HS-4 oscillation; pass_id present

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| CFP-B1 | P1 | unambiguous | Contract hard → manifest (match fuse_pass) | YAML | 2 | no |
| CFP-B2 | P1 | unambiguous | Note openai seam / retier honesty | contract/docs | 2,4 | no |

## Defaults inventory impact

- same connector_fuse landmine as fuse_pass

## target_status

`draft` — Wave 2 applied CFP-B1/B2
