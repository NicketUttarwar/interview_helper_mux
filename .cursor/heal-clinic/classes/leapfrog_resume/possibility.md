# Possibility Map — leapfrog_resume

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: hint_only_if_named

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## Plain-language summary

- In one sentence, what is broken: **Order rules exist (`MUST_PRECEDE` + clamp), but not every resume/schedule path is forced through them — and wrong_pin Option E’s “loose” allowlist checklist can skip the full MUST_PRECEDE walk.**
- In one sentence, what “fixed” looks like: **No stage runs or heal-lands past an incomplete required producer; one clamp/schedule gate shared by Partial and Full-auto.**

---

## 1. Mechanism census (HEAD)

| Surface / function | Role in this class | Tag | Path |
|--------------------|--------------------|-----|------|
| `MUST_PRECEDE` | Declared producer→consumer order table (VO chain expanded) | `IN_CODE` | `delivery_guardrails.py` ~168 |
| `earliest_incomplete_must_precede` | First incomplete producer for a consumer | `IN_CODE` | ~227 |
| `clamp_resume_through_order` | DP-LAYUP-ADJ: never resume past VO/MUST_PRECEDE hole | `IN_CODE` | ~278 |
| `VO_ORDER_CLAMP_STAGES` / `VO_CHAIN_DOWNSTREAM_PINS` | Who gets clamped | `IN_CODE` | ~251 |
| `defer_until_producers_ready` / `filter_delivery_candidates` | Schedule-time defer | `IN_CODE` | guardrails + callers |
| Agenda reinject | Reinject incomplete MUST_PRECEDE producers into walk | `IN_CODE` | `homunculus/agenda.py` ~2316 |
| `resume_producer` | Applies clamp for VO clamp/downstream pins | `IN_CODE` | `thrash_hardening.py` ~160 |
| `_heal_navigate_ungated` early returns | Some paths clamp; incompleteness before premature can still walk oddly | `IN_CODE` | thrash_hardening |
| `heal_pin_authority` loose checklist | Specialty/premature_cap skip full MUST_PRECEDE (wrong_pin E) | `IN_CODE` | `heal_pin_authority.py` |
| `stage_minimum_run_checklist` | Happy-path gate **exported, not agenda-wired** | `IN_CODE` | heal_pin_authority (residual from wrong_pin) |
| Direct `from_stage=` setters | May bypass clamp (remutate / recovery / driver) | `IN_CODE` | e.g. `edl_narrative_remutate.py`, `recovery_controller.py`, runner |

**Declared vs actual:** Cousin matrix says LAYUP-ADJ **closed**. HEAD has clamp + matrices. **Residual:** not all resume writers call clamp; schedule checklist unwired; E loose allowlist can admit a pin that still leapfrogs if proposal skipped clamp. Tag: `CODE_DOC_CONFLICT` (closed family vs remaining escape hatches).

---

## 2. Failure permutations

| Case | What happens now | Honest outcome should be | Tag | Pointer |
|------|------------------|--------------------------|-----|---------|
| clean recover | Clamp + filter defer synth→layup/adjudicate | Same | `IN_CODE` | `test_must_precede_order.py` LAYUP |
| wrong target | wrong_pin class (authority) | Refuse / allowlisted only | `IN_CODE` | heal_pin_authority |
| leapfrog VO chain | Clamp on VO/downstream pins | Earliest MUST_PRECEDE hole | `IN_CODE` | `clamp_resume_through_order` |
| leapfrog via schedule | Agenda may still enqueue consumer if reinject incomplete | Defer consumer; run producer | `IN_CODE` | agenda + defer_until |
| leapfrog via ungated from_stage | Remutate/recovery set stage string directly | Must clamp or refuse | `IN_CODE` | remutate / recovery |
| leapfrog via E loose allowlist | Checklist skips MUST_PRECEDE for g0/voice/fuse/premature_cap | Still clamp proposal before admit | `IN_CODE` | heal_pin_authority `_loose` |
| hollow success | Hollow done on adjudicate then synth “legal” | hollow_pass class | — | cousin |
| Partial must-act | Gate open should not schedule past gate producer | Stay / wait gate | `IN_CODE` | Partial guards |
| Full-auto defaults | Same MUST_PRECEDE; automation rewrite still should clamp | Shared | `IN_CODE` | apply_premature_cap → resolve |

---

## 3. Already closed vs residual

| Prior DP / cousin_matrix row | Claimed closed? | Verified on HEAD? | Residual? |
|------------------------------|-----------------|-------------------|-----------|
| DP-LAYUP-ADJ A MUST_PRECEDE+clamp | closed | **Yes** — table + clamp + filter tests | Escape hatches remain |
| DP-VO1 ladder | closed | **Yes** (related) | — |
| wrong_pin E authority | implemented this campaign | **Yes** | Loose checklist can weaken leapfrog defense |
| Agenda schedule checklist | wrong_pin residual | **Exported only** | **Yes** |
| All from_stage writers → clamp | not claimed closed | **Partial** | **Yes — primary residual** |
| Non–VO-chain stages (analysis leapfrog) | thin | `UNKNOWN` / thin tests | Possible secondary |

HINT only: exec_13163 VO identical storms — verify-or-drop; do not treat as HEAD proof.

---

## 4. Complexity traps

- **Two gates:** heal clamp vs schedule defer — can disagree.
- **Clamp set membership:** stages outside `VO_ORDER_CLAMP` / `VO_CHAIN_DOWNSTREAM` are not clamped.
- **HAU speech-first:** mix MUST_PRECEDE skips beds — intentional; not leapfrog if documented.
- **OpenAI:** not the root; host order honesty is.

---

## 5. TEST_GAP

| Behavior | Covered? | Suggested matrix test |
|----------|----------|------------------------|
| Synth/adjudicate/layup filter | **Yes** | `test_must_precede_order.py` |
| Downstream music clamps when VO hole | **Yes** | `test_footgun_harden_pass.py` |
| Every public from_stage writer clamps | **Gap** | Caller census matrix / lint |
| heal_navigate allowlisted pin always clamp-equivalent | **Thin** | Authority + clamp assert |
| Agenda never schedules past MUST_PRECEDE hole | **Thin** | schedule + `stage_minimum_run_checklist` |
| Partial vs Full-auto same clamp | **Gap** | Shared fixtures |

---

## 6. Cousin hints

- **wrong_pin** (done E) — feed: refuse bad pins; residual: wire schedule checklist + clamp-on-admit for loose allows
- **hollow_pass** — hollow adjudicate makes leapfrog look “legal”
- **post_heal_budget_thrash** — leapfrog → identical/budget
- **heal_validate_stage_fail** — validate on leaped stage

Bigger deterministic shared rule: **`admit_resume(ctx, stage)`** = clamp + authority + schedule checklist; only API for from_stage / candidate filter.

---

## 7. Ready for options?

- [x] Census complete enough for A/B/C
- [x] Surgical vs bigger SSOT imaginable

See [options.md](options.md).
