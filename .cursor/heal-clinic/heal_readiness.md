# Heal readiness — Wave 3 rollup

status: complete  
brain: 0.2.0 | written: 2026-09-22  
code_is_king: true | prior_exec: hint_only (none named this campaign)  
basis: ledger L3=implemented for all five classes + HEAD modules below  

## Plain-language verdict (operator-facing)

- Odds for error-free **Partial** on HEAD: **Meaningfully higher** than pre-clinic — the five heal-variance lies (wrong pin, leapfrog, hollow done, false recover, success-as-thrash-fuel) now have host SSOTs. Not a guarantee of tape quality or first-try finish; orchestration honesty is the claim.
- Odds for quieter **Full-auto / all modes**: **Same direction** — each verdict required Partial=Full-auto law (`FULL_AUTO_REGRESSION_RISK` refused). No Partial-only soft wipe shipped.
- Biggest residual heal risk: **Allowlist / exception drift** (RECOVER_PLAYBOOK_ALLOW, pin allowlists, POST_HEAL_EPOCH_ALLOW empty-by-design) and **P6** (walk max_invokes still not reset on recovered — BUD-1 product flip only). Listen-delight / live soak remain outside this clinic.

---

## Per class

| class_id | L1 | Options+verdict | L3 | Residual risk |
|----------|----|-----------------|----|---------------|
| wrong_pin | complete | E | implemented | Pin allowlist content; new navigators must use `resolve_heal_from_stage` |
| leapfrog_resume | complete | B+ | implemented | Admit clamp miss if a schedule path bypasses admit; VO honesty gated on `is_done` in tests |
| hollow_pass | complete | B+ | implemented | Marker-only / force-guard exception tables; new writers must use `try_mark_done` |
| heal_validate_stage_fail | complete | B+ | implemented | RECOVER_PLAYBOOK_ALLOW / SOFT_PRE_FLUSH empty — silent widen reopens false recovered |
| post_heal_budget_thrash | complete | B+ | implemented | P6: walk caps not epoch’d on recover; sticky still sealed/token-only; don’t fill POST_HEAL_EPOCH_ALLOW casually |

---

## Cross-class SSOT landed

All five patterns **implemented** on HEAD (`IN_CODE`):

| Pattern | Module / entrypoint | Role |
|---------|---------------------|------|
| HC-PIN-NAV | `heal_pin_authority.resolve_heal_from_stage` / `admit_resume` | Refuse-by-default heal pin |
| HC-LEAP-ADMIT | Admit Constitution (clamp + schedule + honest ready) | No leapfrog past MUST_PRECEDE |
| HC-HOLLOW-DONE | `done_authority.try_mark_done` + producer_ready widen | Marker ≠ honest primary |
| HC-HEAL-SUCCESS | `heal_success.finalize_heal_success` | recovered only if predicate + seed + admit |
| HC-POST-HEAL-BUDGET | `heal_post_accounting.finalize_post_heal_accounting` | success ≠ thrash fuel; P3 predicate reclaim |

Stack (simple language):

```
Pin correctly (PIN)
  → Admit schedule/resume (ADMIT)
  → Stamp only when primary real (DONE)
  → Say recovered only when hole gone (HEAL-SUCCESS)
  → Don’t treat that success as identical/budget thrash (POST-HEAL)
```

See [cross_class_patterns.md](cross_class_patterns.md).

---

## Code-based confidence (not live soak)

| Check | Result | Tag |
|-------|--------|-----|
| Five ledger rows L3=`implemented` | Yes | pack SSOT |
| Entrypoint modules present on HEAD | `heal_pin_authority`, `heal_success`, `heal_post_accounting`, `done_authority` | `IN_CODE` |
| Clinic cascade tests exist | `test_heal_pin_authority`, `test_admit_constitution`, `test_done_constitution`, `test_heal_success`, `test_heal_post_accounting` (+ adapted cousins) | `IN_CODE` |
| Mode parity doctrine | Each B+/E packet forbade Partial-only soft clear | pack + code |
| Live Mohan Partial finish proof | **Not claimed** | out of clinic |

---

## Residual cousins (suggestions — not open clinic classes)

| Residual | Why it still matters | Where it lives |
|----------|----------------------|----------------|
| Walk `max_invokes` after honest recover (P6) | Intentional anti-C; product flip reclaim only | BUD-1 / `homunculus/budget` |
| Allowlist sprawl | New playbooks / pins if added without gate | RECOVER_* / pin allow tables |
| Sticky / ESR soft-continue | Can delay halt while work continues | `thrash_hardening` / ESR |
| Per-stage listen quality | Heal honesty ≠ listen-delight | Debug / product quality |
| Live soak | Tape proof separate from clinic | Full-auto or Partial run |

---

## Not claimed here

- Live Mohan soak proof (separate from this clinic)
- Tape listen-delight / MusicGen / MMAudio quality (Debug / product quality lane)
- That every future stage never fails — failures must stay **honest**
- Infinite retry after heal (explicitly rejected as Option C / anti-C)

---

## Operator do-not list (post-clinic)

1. Do not silent-widen `RECOVER_PLAYBOOK_ALLOW` / `SOFT_PRE_FLUSH_ALLOW` / `POST_HEAL_EPOCH_ALLOW`
2. Do not stamp `budget_epoch` on every `recovered` (reopens thrash)
3. Do not bypass Admit / Done / Heal Success / Post-Heal entrypoints with local specials
4. Do not treat clinic close as soak proof — optionally companion-watch a Partial run outside this pack

---

## Campaign status

| Wave | Status |
|------|--------|
| 0 Framework | complete |
| 1 Discover + options (five classes) | complete |
| 2 Implement (five verdicts) | complete |
| 3 Readiness | **complete** (this file) |

Ledger: [ledger.md](ledger.md) · STEP_OFF: [STEP_OFF.md](STEP_OFF.md)
