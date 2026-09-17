# Target Spec — air_script_compose

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| enable + selection | Deterministic Pass A; heal | Completes |
| enable=false | Explicit skip latch + done | Completes |
| selection_commit_refused | Incomplete | Honest |
| hollow VO seats | OK at Pass A (HR-3) | Completes |

## Rules set

- deterministic Pass A; seats deferred to seams
- disabled → skip-done
- automation fail_closed documented

## Complexity subtraction

- No LLM at Pass A

## Acceptance checks

- HR-3; enable false heal; fail_open automation

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| ASC-B1 | P0 | unambiguous | Contract tier process not llm_full | YAML | 2 | no |
| ASC-B2 | P0 | unambiguous | Disabled path heal/skip-done | air_script.py | 1,3 | yes |
| ASC-B3 | P2 | needs_you | Pass A may shrink selection via omit? | intent | 7 | no |

## Defaults inventory impact

- `mastering.air_script.enable=true`; automation fail_closed landmine

## target_status

`draft`
