# Target Spec — sfx_prompt_craft

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| craft success + green QA | prompts + auto-approve | Continues to mmaudio |
| craft success + warnings | incomplete OR explicit auto-approve policy | No silent stall |
| enabled=false | skip done honest | Continues |

## Rules set

- admit / refuse LLM / incomplete hollow prompts
- auto_resolve_default: Full-auto approve when product says so
- wait_for_gate only Partial when G1.5 required

## Complexity subtraction

- One approve policy for Full-auto vs first_try-only auto

## Acceptance checks

- no duplicate prompts on re-craft
- mmaudio blocked until approved when flag true
- Full-auto does not hang forever on G1.5

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Fix contract consumers → mmaudio_sfx | dependency data | 7 | no |
| B2 | P0 | needs_you | Full-auto G1.5 auto-approve policy beyond first_try green | defaults inventory | 3,5 | yes |
| B3 | P1 | unambiguous | Refuse default_SDP empty assets | input check | 2 | no |

## Defaults inventory impact

- `g1_5_require_prompt_approval=true` — stage-local landmine for unattended product Full-auto

## target_status

`draft`
