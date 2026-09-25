# Possibility Map — heal_validate_stage_fail

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: hint_only_if_named

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## Plain-language summary

- In one sentence, what is broken: **Heal / flush / recovery can say “ok / recovered / pass” while the hole that failed is still open** — soft pre-flush, after-flush that does not hard-halt on acceptance `retry`, and playbooks that set `recovered=True` without proving the predicate flipped — so the same (or next) stage fails again.
- In one sentence, what “fixed” looks like: **No surface reports heal success unless Done Constitution readiness holds** (`seed_stage_complete` / `producer_ready`) **and** the original fail predicate is gone; soft validate cannot unlock `mark_done` or `status=recovered`.

---

## 1. Mechanism census (HEAD)

| Surface / function | Role in this class | Tag | Path:line |
|--------------------|--------------------|-----|-----------|
| `heal_or_refuse_mark` | Mark/unmark; flush then incompleteness; “ok” = marked or done | `IN_CODE` | `stage_completion.py:2682–2804` |
| `heal_or_raise` | Raises on refuse; success if marked **or** bare `is_done` | `IN_CODE` | `stage_completion.py:2807–2819` |
| `validate_staged_before_flush` | Pre-flush soft-pass on empty/cannot-read; can override acceptance fail | `IN_CODE` | `stage_resilience.py:187–243` |
| `evaluate_stage_resilience` / `after_flush_resilience` | Acceptance fail → `retry`/`escalate`, **not** always `halt` | `IN_CODE` | `stage_resilience.py:69–184` |
| `approve_stage_writes` | Raises only if `post.action == "halt"` — **retry still `mark_done`** | `IN_CODE` | `write_staging.py:1638–1644` |
| `vo_synthesize_should_defer_done` | Incomplete VO flush without mark (fail-open) | `IN_CODE` | `write_staging.py:1607–1637` |
| `handle_stage_failure` | Playbook → `status=recovered` without re-checking seed-complete | `IN_CODE` | `recovery_controller.py:1381–1948` |
| Unconditional `recovered = True` | e.g. `sdp_theme_wavs_missing` always recovered | `IN_CODE` | `recovery_controller.py:1612–1615` |
| HE-2 honest refuse | `vo_audibility_drift` recovers only when sanitary | `IN_CODE` | `recovery_controller.py:1776–1786` |
| Pipeline on recovered | Re-runs **same** failed stage (ignores `resume_stage`) | `IN_CODE` | `pipeline.py:655–677` |
| Homunculus on recovered | Recurses to `resume_stage` (depth ≤2) | `IN_CODE` | `homunculus/runtime.py:316–335` |
| Driver `_try_recovery` | Returns `resume_stage` on recovered — no seed gate | `IN_CODE` | `tools/full_auto_driver.py:849–862` |
| Driver `_execute_after_heals` | **Does** require `seed_stage_complete` after heal mark | `IN_CODE` | `full_auto_driver.py:59–86` |
| Identical-failure ledger | Skipped when `recovered` → false recover bypasses ×3 halt | `IN_CODE` | `recovery_controller.py:1924–1945` |
| Sticky heal | Same pin+predicate ×N halt (symptom cap) | `IN_CODE` | `thrash_hardening.py:1290–1426` |
| Done Constitution | Stamp / ready honesty (hollow_pass B+) | `IN_CODE` | `done_authority.py`, `producer_ready` |
| Admit Constitution | Pin/schedule clamp (leapfrog B+) — not post-heal success gate | `IN_CODE` | `heal_pin_authority.py` |
| `soft_pass_pre_edl_delivery` | Refuse stubs unless last-resort | `IN_CODE` | `full_auto_driver.py:7577–7602` |
| SDP_CUE_SLOTS cousin | Cue-slot heal-pass/stage-fail family claimed closed | `CODE_DOC_CONFLICT` vs class residual | `soundscape_policy.py` cue-slot SSOT |

**Declared vs actual:** Done Constitution closed **stamp** lies; driver skip-ahead after heals requires seed-complete. **Residual:** recovery `recovered`, resilience soft/pre_flush, after_flush `retry≠halt` still advertise success without Done Constitution. Ledger note “Must plug into Done Constitution ready” is accurate (`CODE_DOC_CONFLICT` if docs imply class closed).

---

## 2. Failure permutations

| Case | What happens now | Honest outcome should be | Tag | Pointer |
|------|------------------|--------------------------|-----|---------|
| clean recover | Playbook fixes hole; re-run passes; HE-2 sanitary | Same | `IN_CODE` | HE-2 |
| wrong target | Recovered + wrong pin | wrong_pin / admit | `IN_CODE` | wrong_pin |
| leapfrog | Recovered + resume past hole | admit_resume | `IN_CODE` | leapfrog |
| hollow success | Marker without primary | Done Constitution | `IN_CODE` | hollow_pass |
| pre-flush soft | Empty staged → soft pass → later fail | Halt / discard staged | `IN_CODE` | `validate_staged_before_flush` |
| after_flush retry | Acceptance fail → retry → still mark_done | Halt / refuse mark | `IN_CODE` | `approve_stage_writes` |
| false recover (unconditional) | e.g. SDP themes always recovered | recovered iff hole gone + seed-complete | `IN_CODE` | `:1612–1615` |
| false recover (pending barrier) | Lists pending as artifacts | recovered iff flushed | `IN_CODE` | pending barrier playbook |
| pipeline same-stage retry | recovered → re-run consumer not producer | Prove predicate clear **or** resume producer | `IN_CODE` | `pipeline.py:655–677` |
| identical loop | False recovered skips identical×3 | Count failed re-entry / refuse recovered | `IN_CODE` | identical ledger |
| soft_pass / e2e | Without last-resort: no marks | Same | `IN_CODE` | soft_pass |
| Partial / Full-auto | Same host bugs; last-resort env risk | Shared honesty | `IN_CODE` | e2e_soft |
| post-success budget | False recover burns invoke budget | post_heal_budget_thrash | — | cousin |

---

## 3. Already closed vs residual

| Prior DP / cousin_matrix row | Claimed closed? | Verified on HEAD? | Residual? |
|------------------------------|-----------------|-------------------|-----------|
| Done Constitution / hollow_pass B+ | stamp closed | **Yes** | Does **not** gate recovery `recovered` |
| Driver `_execute_after_heals` seed-complete | skip-ahead closed | **Yes** | Recovery/pipeline don’t use it |
| HE-2 VO-audibility honesty | closed for that class | **Yes** | Pattern not generalized |
| soft_pass refuse without last-resort | closed | **Yes** | Last-resort stubs if env set |
| SDP_CUE_SLOTS heal-validate↔stage-fail | closed (cue family) | **Yes** for cue_slots | **Class residual elsewhere** |
| Identical ×3 / sticky halt | supervisor closed | **Yes** | Bypass when false recovered |
| Unified “recovered ⇒ predicate clear + seed-complete” | **not claimed** | **Absent** | **Primary residual** |
| after_flush halt vs retry wiring | not claimed | **Mismatch on HEAD** | **Primary residual** |

---

## 4. Complexity traps

- Three “success” languages: resilience `pass`, recovery `recovered`, Done Constitution `seed_stage_complete` — only the last is honest advance.
- Pipeline vs homunculus vs driver disagree on what recovered means (same stage vs resume_stage).
- Identical ledger blind spot feeds **post_heal_budget_thrash**.
- OpenAI not root — host validate/recover honesty is.

---

## 5. TEST_GAP

| Behavior | Covered? | Suggested matrix (`MUX_FORENSICS=0`) |
|----------|----------|--------------------------------------|
| HE-2 unsanitary ≠ recovered | **Yes** | `test_he2_edl_heal_playbook.py` |
| soft_pass refuse | **Yes** | `test_r4_premature` / soft_pass tests |
| identical ×3 / sticky | **Yes** | unattended / thrash tests |
| Unconditional recovered while hole open | **Gap** | `sdp_theme_wavs_missing` still missing → not recovered |
| Pending barrier recovered without flush | **Gap** | pending present → recovered False |
| after_flush `retry` must not mark_done | **Gap** | resilience retry → raise, no `.stage_done` |
| recovered ⇒ fail predicate clear + seed-complete | **Gap** | Parametrize playbooks |
| Partial vs Full-auto same recovered honesty | **Gap** | Shared fixture |

---

## 6. Cousin hints

| Class | Link |
|-------|------|
| **hollow_pass** (done) | Stamp honesty; this class = next hop (ok without re-prove) |
| **leapfrog_resume** (done) | Admit clamp; false recover resume still leapfrogs unless gated |
| **wrong_pin** (done) | False recover + wrong pin → thrash |
| **post_heal_budget_thrash** | False recovered skips identical → burns budget |

**Shared SSOT idea:** Heal Success Constitution — any `recovered` / flush-pass requires (1) original predicate cleared, (2) `seed_stage_complete(healed_stage)`, (3) failed re-entry still counts. Plug into Done Constitution + Admit — not a fourth brand.

---

## 7. Ready for options?

- [x] Census complete enough for A/B/C
- [x] Surgical: generalize HE-2 (no unconditional recovered) + after_flush halt on acceptance fail
- [x] SSOT: Heal Success Constitution through recovery + `approve_stage_writes` + pipeline resume contract
- Next paste: `/heal-clinic-options CLASS=heal_validate_stage_fail`
