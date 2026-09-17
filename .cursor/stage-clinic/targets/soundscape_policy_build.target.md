# Target Spec — soundscape_policy_build

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| enabled + brief | Valid policy done | Completes |
| brief missing | refuse (raise/incomplete) | Honest stop |
| disabled | Skip stub done | Completes |
| invent blocked + fail_closed | Hard fail or incomplete — not hollow | Honest |

## Rules set

- admit / brief present
- refuse / invalid policy
- incomplete / prefer over silent skip when fail_closed

## Non-goals

- MusicGen/MMAudio quality

## Acceptance checks

- test_soundscape_policy; brief missing path

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P1 | needs_you | fail_closed invent-block → incomplete vs raise | intent | 1,5 | yes if soft |
| B2 | P2 | unambiguous | Brief-missing covered in stage test | pytest | 2 | no |

## Defaults inventory impact

- soundscape.enabled=true; fail_closed=true; strict_slots=true

## target_status

`draft`
