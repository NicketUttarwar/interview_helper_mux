# Target Spec — mastering_research_waves

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| routing missing | Soft-admit OR refuse — not silent conflict | Continues if soft |
| soft delivery absent | Thin fields OK; schema-valid waves.json done | same |
| hollow waves | incomplete | same |

## Rules set

- admit / probes runnable
- refuse / cannot validate primary
- incomplete / HM-1 hollow
- wait_for_gate / N/A
- auto_resolve_default / N/A

## Complexity subtraction

- Duplicate full re-wave inside rollup (share probe helper)

## Contract deltas

- Demote routing hard→soft OR require in body

## Non-goals

- OpenAI inside waves; delivery completeness at analysis

## Acceptance checks

- Body vs contract hard-input test; HM-1 schema

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P1 | unambiguous | Align routing hard claim → soft (body ignores) | hard:[] + allowlist | 7 | no |
| B2 | P2 | unambiguous | Note dual-run with rollup | comment/map | 7 | no |

## Defaults inventory impact

- none

## target_status

`applied` — Wave 2 MRW-B2 + MRW-B1 (Q1A demote routing hard)
