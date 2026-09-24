# Cross-class patterns — Heal Clinic

When the **same footgun** appears in ≥2 classes, prefer **one deterministic host rule** over five one-offs.  
Agent: add rows from `/heal-clinic-suggest-cousins` or options cousin sections.

| Pattern id | Plain name | Classes touched | Proposed shared SSOT | Status |
|------------|------------|-----------------|----------------------|--------|
| HC-PIN-NAV | Multi-navigator heal pin | wrong_pin (+ leapfrog, budget suggested) | One `resolve_heal_from_stage` + refuse-by-default allowlist + prereq checklist (verdict E) | implemented |
| HC-LEAP-ADMIT | Leapfrog past MUST_PRECEDE | leapfrog_resume (+ hollow, budget, validate) | Admit Constitution = clamp + wrong_pin E + schedule + honest ready (verdict B+) | implemented |
| HC-HOLLOW-DONE | Marker ≠ honest primary / ready | hollow_pass (+ leapfrog VO hook, validate) | Done Constitution: all `.stage_done` writers via try_mark_done; restamp honesty; widen producer_ready | implemented |
| HC-HEAL-SUCCESS | Heal/recover says ok while hole open | heal_validate_stage_fail (+ budget thrash) | Heal Success = finalize_heal_success + predicate clear + seed-complete + admit (verdict B+) | implemented |
| HC-POST-HEAL-BUDGET | After true recovered, same-fp thrash still burns identical/max_invokes/sticky | post_heal_budget_thrash (+ all four prior) | Post-Heal Accounting = finalize_post_heal_accounting + P3 predicate reclaim + P11 census (verdict B+ P1–P11) | implemented |
| HC-HOSTED-VO-DUAL | Gap omit vs floor vs EDL/WAV (Cluster C) | wrong_pin cousin (hollow pin); End-A freeze | `hosted_vo_authority` identify + disposition SSOT — forensics dig, not a new heal-clinic class | implemented (forensics) |

Status: `noted` | `options_open` | `verdict_logged` | `implemented` | `rejected`
