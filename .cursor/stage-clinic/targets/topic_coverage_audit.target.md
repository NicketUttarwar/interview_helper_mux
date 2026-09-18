# Target Spec — topic_coverage_audit

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| det path available | Deterministic audit; no OpenAI | Completes |
| else LLM | OF-01 ≤2 then refuse/incomplete | Honest |
| voice_ref open | Never heal-pin this stage | Continues via missing_framing |
| brief missing | refuse | Honest |

## Rules set

- prefer deterministic
- incomplete / hollow audit
- refuse / LLM exhaust without soft-done

## Complexity subtraction

- Dual path OK; keep det first

## Acceptance checks

- HG-4 pin; det vs LLM; delivery_ready

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P1 | unambiguous | Verify ADG invalidates vs contract list | ADG test | 7 | no |
| B2 | P0 | unambiguous | Keep HG-4 voice_ref → missing_framing | existing | 3 | no |
| B3 | P1 | confirmed | Soft-fail LLM → incomplete/refuse (Q2A CSP-05; reverses 2B) | `test_csp05_*` + auto_complete=False | 2,4 | med (LLM path only; det-first OK) |

## Defaults inventory impact

- none new; delivery handoff assert is landmine if analysis incomplete

## target_status

`draft` — TCA-B3 Q2A CSP-05 soft-fail → incomplete/refuse
