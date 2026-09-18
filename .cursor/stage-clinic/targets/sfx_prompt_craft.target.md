# Target Spec — sfx_prompt_craft

brain: 0.2.0 | target_status: done | L3: B1+B2+B3 applied

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| craft success + green QA | prompts + auto-approve | Continues to mmaudio |
| craft success + warnings | Full-auto auto-approve (`auto_full_auto`); Partial/manual wait GUI | No Full-auto stall |
| enabled=false | skip done honest | Continues |

## Rules set

- admit / refuse LLM / incomplete hollow prompts
- auto_resolve_default: Full-auto approve incl. soft warnings; first_try green otherwise
- wait_for_gate only Partial when G1.5 required + soft warnings

## Complexity subtraction

- One approve policy: Full-auto always; first_try green-only for non-Full-auto

## Acceptance checks

- no duplicate prompts on re-craft
- mmaudio blocked until approved when flag true (Partial/manual + warnings)
- Full-auto does not hang forever on G1.5 (auto-approve incl. soft warnings)

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Fix contract consumers → mmaudio_sfx | dependency data | 7 | no |
| B2 | P0 | unambiguous | Full-auto G1.5 auto-approve incl. soft warnings | operator binding 2026-09-17 | 3,5 | yes (accepted) |
| B3 | P1 | unambiguous | Refuse default_SDP empty assets | input check | 2 | no |

## Defaults inventory impact

- `g1_5_require_prompt_approval=true` — Full-auto product path auto-approves (incl. soft warnings); Partial may still stall GUI

## target_status

`done` — Wave 2 B1+B2+B3 applied
