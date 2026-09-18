# Target Spec — speaker_roles

brain: 0.2.0 | target_status: draft  

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| OpenAI ok | schema-valid speakers + done | ≤2 attempts |
| OpenAI schema fail | refuse StageError (no hollow) | walk remediation |
| spine hard claim | align contract soft OR body require | no false PRESTAGE |

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| B1 | P1 | unambiguous | Soften contract hard spine(when) to soft — body never requires it | contract conformance | 2 | no |
| B2 | P2 | unambiguous | Document fallback_speakers_artifact as intentional Full-auto honesty path | map note / test | 4 | no |

## target_status

`draft` — Wave 2 applied SR-B1/B2 (spine soft; fallback documented)
