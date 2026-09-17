# Target Spec — narrative_arc_plan

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| det path available | Deterministic plan; no OpenAI | Completes |
| else LLM | ≤2 then refuse/incomplete | Honest |
| coverage/brief missing | refuse | Honest |
| hollow chapters | incomplete / no done | Honest |

## Rules set

- prefer deterministic when TP+cuts
- admit if chapters≥1
- refuse hollow / LLM exhaust
- precise invalidate hitch+pre_ranking+ranking

## Complexity subtraction

- Keep dual path; prefer det first

## Acceptance checks

- det vs LLM; checker hard inputs; no GUI wait

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| NAP-B1 | P1 | unambiguous | Align contract hard with `_check_narrative_arc_plan` (coverage+brief) | contract YAML | 2 | no |
| NAP-B2 | P2 | needs_you | QC writer SSOT hitch vs narrative | ownership | 7 | no |

## Defaults inventory impact

- none new; det narrative default is landmine if flipped off

## target_status

`draft`
