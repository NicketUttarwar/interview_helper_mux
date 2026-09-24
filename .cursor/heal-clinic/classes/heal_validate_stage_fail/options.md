# Options packet — heal_validate_stage_fail

status: decided  
verdict: B+  
L3: implemented  
class_plain_name: Heal-validate then stage-fail  
brain: 0.2.0 | code_is_king: true  
written: 2026-09-22  
revised: 2026-09-22 — B+ footgun-complete (V9–V11, finalize_heal_success, single identical policy)  
decided: 2026-09-22 — VERDICT=B+ (see decisions.md)  
implemented: 2026-09-22 — Heal Success Constitution (see decisions.md L3 row)

## TL;DR (read this first — simple language)

- What’s going wrong: Heal / flush / recovery can say **ok / recovered / pass** while the hole that failed is **still open**. The same stage (or the next one) fails again — identical loops that look like “heal worked.”
- What you’d notice: Recovery log says recovered; then the same error; sticky thrash; or budget burns. Soft pre-flush or after-flush `retry` still stamps done.
- Why it matters: False success skips identical×3 halt and poisons Partial **and** Full-auto. Done Constitution fixed **stamps**; this class is the **next hop** — “success” after heal.
- **Agent recommendation:** Option **B+** (complete Heal Success Constitution) — plug into Done Constitution + Admit (not a fourth brand); close every residual row, mode-wide.
- What that gives up: Bigger Wave 2 than surgical HE-2-only; some aggressive “always recover” playbooks become honest stops.

---

## Problem overview (simple language)

### The lie in one picture

```
Stage fails (real hole)
        ↓
Heal / flush / playbook says “ok / recovered / pass”
        ↓
Hole still open (predicate not flipped; soft validate; retry≠halt)
        ↓
Same stage fails again  OR  next stage fails
        ↓
Identical ledger skipped → thrash / budget burn
```

### Already mostly fixed (don’t re-litigate)

| Already strong | Meaning |
|----------------|---------|
| Done Constitution (hollow_pass B+) | Stamps / ready honesty |
| Admit Constitution (leapfrog B+) | Pin/schedule clamp |
| wrong_pin E | Refuse-by-default sideways pins |
| HE-2 VO-audibility | One playbook recovers only when sanitary |
| soft_pass refuse without last-resort | No stub marks |
| Driver `_execute_after_heals` | Skip-ahead needs seed-complete |
| SDP_CUE_SLOTS family | Cue-slot heal-pass/stage-fail closed |

### Residuals this class owns

| # | Residual | Plain English |
|---|----------|---------------|
| V1 | Unconditional `recovered=True` | Playbook ran ≠ hole gone (e.g. SDP themes) |
| V2 | Weak recovered (`bool(artifacts)` / pending list) | “Artifacts” that are error strings still count as success |
| V3 | after_flush `retry` still `mark_done` | Acceptance fail doesn’t halt approve path |
| V4 | Pre-flush soft-pass | Empty/unreadable staged → pass → later fail |
| V5 | Pipeline ignores `resume_stage` | Recovered re-runs failed consumer, not producer |
| V6 | Identical ledger bypass | False recovered skips ×3 halt |
| V7 | Driver/homunculus recover without seed gate | Unlike `_execute_after_heals` |
| V8 | Mode parity | Partial = Full-auto same success law |

### How this plugs into shipped work

```
Heal / recover / flush “success”
  → original fail predicate cleared
  → seed_stage_complete (Done Constitution)
  → resume_stage through admit_resume (Admit)
  → only then status=recovered / mark_done / skip identical
```

Pattern id: **HC-HEAL-SUCCESS** (extends Done + Admit — not a fourth SSOT name).

---

## Options at a glance

| Option | One-line idea | Best if you want… | Worst trade-off |
|--------|---------------|-------------------|-----------------|
| A — Surgical | Generalize HE-2 + fix after_flush halt; kill top unconditional recovered | Fast | Leaves soft pre-flush / pipeline / identical gaps |
| B — Heal Success (thin) | One gate: recovered ⇒ seed-complete + predicate clear | Core idea | Fuzzy “targeted” escapes |
| **B+ — Complete Heal Success** *(recommended)* | Thin B + V1–V8 mandatory + censuses + Partial=Full-auto | Thorough, all modes | Largest Wave 2 for this class |
| C — Never auto-recover | recovered always false; operator/manual only | Max honesty | Finish rate crash |
| Defer | Soak after hollow/leapfrog | Evidence | False recover still burns night runs |

---

## Option A — Surgical

**What we would do:**

1. Kill unconditional `recovered = True` playbooks (start with `sdp_theme_wavs_missing`) — recovered iff hole gone (HE-2 pattern).
2. In `approve_stage_writes`: treat acceptance fail / `retry` like `halt` (no `mark_done`).
3. Matrix tests for those two sites.

**Pros:** Small; hits loud residuals.  
**Cons:** Soft pre-flush, pipeline resume, identical bypass, driver gate remain.

**Real-world worst case:** Another unconditional playbook or soft pre-flush still greenlights → same loop.

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium–high for patched sites |
| All-modes | Shared |
| Cousin closure | Low–medium (budget still open) |
| Implement cost | Low |
| FULL_AUTO_REGRESSION_RISK | no |

---

## Option B — Bigger deterministic (thin)

**What we would do:**

One helper, e.g. `assert_heal_success(ctx, stage, *, fail_predicate_clear: bool)`:

- Requires `seed_stage_complete(stage)` (Done Constitution)
- Requires caller-proven predicate clear
- `handle_stage_failure` may set `recovered` only through this helper
- Wire `_try_recovery` / pipeline recovered path to same gate

**Pros:** Right shape; plugs into Done.  
**Cons:** Without mandatory residual checklist, implement will leave V3–V6 fuzzy (same problem as thin hollow B).

**Real-world worst case:** Helper exists but soft flush / pipeline still bypasses it.

---

## Option B+ — Complete Heal Success Constitution *(recommended)*

Footgun-complete for implement (same bar as hollow_pass B+).

### 1. One law (Partial + Full-auto identical)

```
recovered / flush-pass / heal “ok”
  → fail predicate cleared via SSOT API (not free prose)
  → seed_stage_complete on the correct stage (see §1b)
  → resume_stage = admit_resume(...)                 # Admit Constitution
  → only then: status=recovered / mark_done
```

Single entrypoint for all callers (pipeline / homunculus / driver):

`finalize_heal_success(ctx, *, failed_stage, resume_stage, playbook_id, predicate_clear) -> HealSuccessResult`

Extend `done_authority` (or thin helper beside it) — **HC-HEAL-SUCCESS**. Not a fourth brand.

### 1b. Which stage must be seed-complete? (no waffle)

| Path | Seed-complete required on |
|------|---------------------------|
| Resume to producer | **Producer pin** after `admit_resume` |
| Same-stage retry | **Failed stage**, and only if playbook ∈ SAME_STAGE_RETRY_ALLOW **and** predicate clear |
| Flush → mark_done | **Stage being marked** must be seed-complete-eligible (outputs + incompleteness); bare `is_done` never counts |

### 1c. Predicate-clear SSOT (no free prose)

One API, e.g. `heal_fail_predicate_clear(ctx, error_class, *, detail) -> bool`:

- Re-classify / re-check incompleteness / named checker for that error_class  
- Playbooks do **not** invent ad-hoc “looks fixed” booleans  

### 1d. Identical ledger policy (single choice)

**Refuse false recovered** — do not dual-path “or still increment.” If gate fails → `recovered=False` and identical/sticky accounting proceeds normally.

### 2. Mandatory residual closure (all ✅ or named exception)

| ID | Work | Done means |
|----|------|------------|
| V1 | Census unconditional `recovered=True` | Each → gate or deleted; only RECOVER_PLAYBOOK_ALLOW may recover |
| V2 | Weak `recovered=bool(artifacts)` | Artifacts must prove hole closed (not error strings) |
| V3 | after_flush acceptance fail | No mark_done unless halt-equivalent |
| V4 | Pre-flush soft empty/unreadable | Halt or discard; never unlock done |
| V5 | Pipeline recovered contract | `finalize_heal_success` + admit resume **or** same-stage allow |
| V6 | Identical ledger | False recovered refused (see §1d) |
| V7 | Driver + homunculus | Same `finalize_heal_success` as pipeline |
| V8 | Mode parity tests | Partial = Full-auto |
| V9 | VO / fail-open flush | Fail-open cannot count as heal success / cannot unlock consumers |
| V10 | `heal_or_raise` success | ≡ seed-complete (not bare `is_done`) |
| V11 | Soft cross-validate | Soft ≠ recovered / ≠ advance success |

### 3. Exception tables (required)

| Table | Purpose |
|-------|---------|
| **RECOVER_PLAYBOOK_ALLOW** | Only listed playbooks may set recovered — and only through the gate |
| **RECOVER_ALLOW_WITHOUT_SEED** | Default **empty** |
| **SOFT_PRE_FLUSH_ALLOW** | Default empty or log-only (no done unlock) |
| **SAME_STAGE_RETRY_ALLOW** | Rare; must prove predicate clear |
| **LAST_RESORT_SOFT** | Never sets `recovered`; documented stub-only |

### 4. Censuses (pack + lint tests)

- Recover census: every `recovered =` / `status=recovered`  
- Flush-success census: resilience pass → `mark_done`  
- Caller matrix: pipeline / runtime / driver all call `finalize_heal_success`

### 5. Cousin plug-in

| Cousin | B+ requirement |
|--------|----------------|
| hollow_pass | seed-complete is the success floor |
| leapfrog / wrong_pin | resume through admit_resume |
| post_heal_budget_thrash | Same success gate; **no second thrash counter** |

### 6. Tests (`MUX_FORENSICS=0`)

- V1–V11 matrix rows above  
- Positive: HE-2-style sanitary playbook **may** recover when gate green  
- Census lint + caller matrix lint  
- Partial vs Full-auto parity  

**Pros:** Thorough; footgun-closed; feeds budget class.  
**Cons:** Largest Wave 2 for this class.  

**Real-world worst case:** Over-strict gate stops a true recoverable playbook — mitigate with RECOVER_PLAYBOOK_ALLOW + positive HE-2 tests.

| Axis | Assessment |
|------|------------|
| Partial certainty | **Highest** |
| Full-auto / all-modes | **Highest** |
| Cousin closure | **High** |
| Implement cost | Highest |
| FULL_AUTO_REGRESSION_RISK | **no** if shared |

---

## Option C — Never auto-recover

**What we would do:** `recovered` always false; playbooks only log; operator or fresh from_stage only.

**Pros:** Max honesty.  
**Cons:** Unattended finish rate collapses.  

**Real-world worst case:** Partial night runs stop on every recoverable OpenAI/schema glitch.

| Axis | Assessment |
|------|------------|
| Partial certainty | High honesty, low finish |
| FULL_AUTO_REGRESSION_RISK | **yes** — more stops |

---

## Option Defer

Soak after hollow/leapfrog only. **Risk:** False recover still burns budget and identical loops — conflicts with thoroughness ask.

---

## Recommendation (not a decision)

- Preferred: Option **B+**
- Why for error-free Partial: False “heal ok” is the upstream poison for identical loops and budget thrash; stamps alone (hollow) don’t close it.
- Why all modes: Same success law Partial and Full-auto; reuse Done + Admit.
- Honest downside: Larger implement; some playbooks that “always recovered” will stop honestly until fixed.
- Devil’s-advocate: Pick **A** for a one-evening patch, then immediately options on **post_heal_budget_thrash**. Pick thin **B** only if you accept fuzzy V3–V6 at implement time.
- Phased custom: `custom:B+ phase1=V1+V3+V8; phase2=V2+V4+V5+V6+V7`

---

## Cousins to investigate next

| Class id | Why | Shared SSOT? |
|----------|-----|--------------|
| post_heal_budget_thrash | False recovered → budget burn | yes — HC-HEAL-SUCCESS |
| hollow / leapfrog / wrong_pin | Already implemented — B+ plugs in | already |

---

## Evidence appendix

- Map: [possibility.md](possibility.md) · dossier: [dossier.md](dossier.md)
- HEAD: `recovery_controller.handle_stage_failure`, `stage_resilience`, `write_staging.approve_stage_writes`, `pipeline` recovered path, `done_authority`, `heal_pin_authority.admit_resume`
- Hints: SDP_CUE_SLOTS closed family ≠ this class closed; HE-2 pattern to generalize

---

## Your verdict (operator fills)

- choice: **B+**
- notes: Footgun-complete Heal Success Constitution — V1–V11; finalize_heal_success for pipeline/runtime/driver; Done + Admit plug-in; refuse false recovered
- date: 2026-09-22

## YOUR NEXT ACTIONS

1. L3 done — paste `/heal-clinic-next` for **post_heal_budget_thrash**.
2. Do **not** silent-widen `RECOVER_PLAYBOOK_ALLOW` / `SOFT_PRE_FLUSH_ALLOW`.

```
/heal-clinic-next
Follow .cursor/skills/heal-clinic/SKILL.md
Read .cursor/heal-clinic/STEP_OFF.md, queue.md, ledger.md.
Pick next open class per skill algorithm. Discover or options as needed.
Simple language. No product patches. End with YOUR NEXT ACTIONS.
```
