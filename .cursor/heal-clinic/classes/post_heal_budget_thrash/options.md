# Options packet — post_heal_budget_thrash

status: decided  
verdict: B+  
L3: implemented  
class_plain_name: Budget thrash after “successful” heal  
brain: 0.2.0 | code_is_king: true  
written: 2026-09-22  
revised: 2026-09-22 — B+ tightened: P3 no-waffle + mandatory caller census (P11)  
decided: 2026-09-22 — VERDICT=B+; P3=ship predicate reclaim; P11=caller census (see decisions.md)  
implemented: 2026-09-22 — Post-Heal Accounting (see decisions.md L3 row)

## TL;DR (read this first — simple language)

- What’s going wrong: Heal can be **honestly recovered** (HC-HEAL-SUCCESS already closed false “ok”), but that success still **burns thrash fuel** — R12c bumps identical counts, recovery attempt budget counts the row, sticky has no recovered hook, and BUD-1 only reclaim on **product fingerprint flip**. Same fingerprint → max_invokes / identical×N / sticky / unstick loops.
- What you’d notice: Recovery log says recovered; minutes later identical halt or `dispatch_cap_refusal` / `budget_exhausted` on the **same** hole family — no code patch happened.
- Why it matters: Unattended Partial / Full-auto die after “we fixed it.” Upstream constitutions closed **lies**; this class closes **accounting after truth**.
- **Agent recommendation:** Option **B+** — mandatory P1–P11; **P3 no waffle** (ship predicate-progress reclaim **or** named exception); **one accounting entrypoint** with full caller census (no silent second path).
- What that gives up: Bigger Wave 2 than “skip R12c on recovered”; must carefully preserve escalate-path halt honesty and RC6 (unstick never zeros identical).

---

## Problem overview (simple language)

### The lie in one picture

```
Hole real → heal playbook runs
        ↓
finalize_heal_success → status=recovered   (honest — hole gone)
        ↓
_append_action still logs + R12c mirrors into identical×N
attempt_count still counts recovered toward recovery budget
sticky / walk max_invokes unchanged (BUD-1 only on product fp flip)
        ↓
Same class fails again OR resume re-dispatch burns caps
        ↓
identical halt / budget_exhausted / sticky / unstick loop
```

### Already mostly fixed (don’t re-litigate)

| Already strong | Meaning |
|----------------|---------|
| HC-HEAL-SUCCESS (heal_validate B+) | False recovered refused; predicate + seed + admit |
| Done Constitution / Admit / wrong_pin E | Stamp / schedule / pin honesty |
| **DP-BUD1 A** | Product fingerprint flip → `stamp_budget_epoch` + memo clear; refuse≠hollow Finished |
| Unstick RC6/O8 | Never zeros identical from unstick (keep) |
| R12c escalate path | Failed recoveries still unify recovery log ↔ identical |

### Residuals this class owns

| # | Residual | Plain English |
|---|----------|---------------|
| P1 | R12c mirrors **recovered** into identical | Success looks like another identical strike |
| P2 | Recovered rows burn `recovery_attempt_budget` | Default budget=1 → next fail is often `budget_exhausted` with no second playbook |
| P3 | Pre-heal identical×N left sitting + no predicate reclaim | “Don’t bump on recovered” alone leaves ×2; next fail still ×3. Must **clear/epoch that signature on token flip** **or** named exception |
| P4 | Sticky ignores recovered | Unsealed pin keeps sticky×N after “ok” |
| P5 | Resume re-dispatch / Complete-before | Extra stage starts toward walk/dispatch caps |
| P6 | Dual invoke laws | `count_identity` vs `count_attempts` — patch one, miss the other |
| P7 | Transient recovered×3 | budget=3 + R12c → structural halt risk even when each recover was honest |
| P8 | Mode / forensics split | Forensics wipes identical; Partial must not get a soft-only escape |
| P9 | Unstick clears thrash not identical | Correct RC6 — but post-heal identical climb remains this class |
| P10 | E2E same-fp storm untested | No matrix: recover once → N starts → cap/halt without product flip |
| P11 | Multi-caller accounting bypass | pipeline / runtime / driver / `_append_action` invent second paths (hollow/validate footgun) |

### How this plugs into shipped work

```
finalize_heal_success → recovered=True
  → ONE entrypoint: finalize_post_heal_accounting(...)   # P11
       success ≠ thrash fuel (P1/P2)
       predicate-progress reclaim for that signature (P3) — or named exception
       sticky: sealed/token only (P4)
  → BUD-1 still owns product-fingerprint reclaim
  → HC-HEAL-SUCCESS still owns “may we say recovered?”
```

Pattern id: **HC-POST-HEAL-BUDGET** — accounting beside BUD-1 + Heal Success (**not** a fifth unrelated brand; do **not** invent a second thrash counter file).

---

## Options at a glance

| Option | One-line idea | Best if you want… | Worst trade-off |
|--------|---------------|-------------------|-----------------|
| A — Surgical | Skip R12c + attempt-budget burn on `status=recovered` | Fast | Leaves sticky, dual caps, P3 reclaim, P5 resume |
| B — Post-Heal Accounting (thin) | One helper: success ≠ thrash fuel | Core shape | Fuzzy escapes on P3–P6 |
| **B+ — Complete Post-Heal Accounting** *(recommended)* | Thin B + P1–P11; P3 no-waffle; one entrypoint census | Thorough, all modes | Largest Wave 2 for this class |
| C — Epoch on every recovered | Always `stamp_budget_epoch` after recovered | Max retry room | Infinite retry / hide stuck holes |
| Defer | Soak after heal_validate | Evidence | Same-fp thrash still burns night runs |

---

## Option A — Surgical

**What we would do:**

1. In `_append_action` / `_mirror_recovery_to_identical_failures`: **do not** R12c-mirror when `status=recovered` (escalate path unchanged).
2. In `attempt_count` / budget checks: **exclude** recovered log rows from `recovery_attempt_budget` fuel (or count only escalate).
3. Adapt `test_unified_recovery_counters_r12c`: recovered must **not** bump identical; escalate still must.
4. Matrix: one recovered then same-class fail still records identical on the **fail** path.

**Pros:** Small; hits loud P1–P2.  
**Cons:** Sticky, walk max_invokes, dual budget laws, predicate reclaim, resume Complete-before remain.

**Real-world worst case:** Recovered no longer fuels identical, but walk `count_attempts` still hits max_invokes after resume re-dispatch — night run still dies; looks “half fixed.”

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium for recovery-identical path |
| All-modes / Full-auto | Shared for A’s sites |
| Cousin closure | Low |
| Complexity left | High (P3–P6) |
| What you give up | Thorough same-fp storm close |
| Implement cost | Low |
| Regression risk | Medium — must not break escalate R12c halt |
| Reversibility | High |
| FULL_AUTO_REGRESSION_RISK | no |

**Tests (`MUX_FORENSICS=0`):** R12c recovered≠bump; escalate still bumps; budget_exhausted after recovered needs a **failed** attempt, not the success row alone.

---

## Option B — Bigger deterministic (thin)

**What we would do:**

One helper beside Heal Success / identical_failures, e.g. `note_heal_success_accounting(ctx, *, signature, status)`:

- If `status=recovered`: do not thrash-fuel identical or recovery-attempt for that row
- Document “BUD-1 still owns product reclaim”
- Call from `_append_action` only

**Pros:** Right shape; one name.  
**Cons:** Without mandatory P3–P10, implement will leave sticky / dual caps / resume / tests fuzzy (same thin-B trap as hollow / validate).

**Real-world worst case:** Helper exists; driver still burns max_invokes; operator thinks class is closed.

| Axis | Assessment |
|------|------------|
| Partial certainty | Medium if only recovery path wired |
| All-modes | Shared if wired everywhere |
| Cousin closure | Medium |
| Complexity left | Medium–high |
| Implement cost | Medium |
| FULL_AUTO_REGRESSION_RISK | no if mode-identical |

---

## Option B+ — Complete Post-Heal Accounting Constitution *(recommended)*

Footgun-complete for implement (same bar as hollow / heal_validate B+).  
**Operator tighten (2026-09-22):** P3 no waffle; P11 mandatory caller census — one entrypoint, no silent second path.

### 1. One law (Partial + Full-auto identical)

```
status=recovered  (only via finalize_heal_success — already shipped)
  → ALL post-success accounting through ONE entrypoint (P11):
       finalize_post_heal_accounting(ctx, *, signature, status, playbook_id, stage_id)
  → success is NOT thrash fuel:
       no R12c identical bump for that recovered row          # P1
       recovered rows do NOT burn recovery_attempt_budget    # P2
  → P3 (HARD — choose at implement, record in decisions.md):
       DEFAULT: ship predicate-progress reclaim for that signature
         when stage_predicate_token flips → clear/zero that signature’s
         identical count and/or stamp identity epoch (reuse existing flip helpers)
       ALTERNATE: named exception in decisions.md explaining why pre-heal
         ×N may remain (do NOT silently leave “don’t bump” as the whole fix)
  → recovered=True alone never stamps epoch / never clears identical   # anti-C
  → sticky: sealed/token only — never clear sticky solely because recovered=True
  → unstick: still never zeros identical (RC6 stays)
  → walk/dispatch caps: both count_identity AND count_attempts honest or named exception
```

**HC-POST-HEAL-BUDGET** plugs into BUD-1 + Heal Success — **not** a fifth SSOT brand and **not** a second `operator/*_thrash.json` counter.

### 1b. P3 — predicate-progress reclaim (no waffle)

**Why “don’t bump on recovered” is not enough:** If identical was already ×2 before the heal, skipping the recovered bump leaves ×2. The next fail is still ×3 halt — success never gave the signature a clean slate.

| Event | Clear that signature’s identical / stamp identity epoch? |
|-------|----------------------------------------------------------|
| `recovered=True` alone | **No** (avoids infinite retry — that is Option C) |
| Product fingerprint flip | **Yes** — BUD-1 unchanged (whole-product / memo) |
| Predicate token **flips** for the healed stage/signature | **Yes — ship this (B+ default)** — clear/zero **that** signature (and identity attempt fuel as designed), reuse `stage_predicate_token` / `predicate_flipped` / existing clear helpers |
| Predicate **unchanged** after recovered | **No** clear — next fail must still count toward halt |
| Unstick / soft thrash clear | **No** identical wipe; **no** silent epoch |

Implement must pick one and log it in `decisions.md`:

1. **Ship** predicate-progress reclaim (recommended default), **or**
2. **Named exception** — one paragraph why pre-heal ×N may remain; still must not pretend P1 alone closed P3.

### 1c. P11 — caller census (one entrypoint; no silent second path)

Same footgun as hollow/validate: helper exists but pipeline / runtime / driver bypass it.

| Caller | Must use `finalize_post_heal_accounting` (or only path that does) | Must not |
|--------|------------------------------------------------------------------|----------|
| `recovery_controller._append_action` / R12c | Yes — sole place recovery log meets identical | Blind `_mirror_recovery_to_identical_failures` on recovered |
| `pipeline` recovered branch | Yes — any post-recover accounting / resume fuel | Local identical bump or ad-hoc epoch |
| `homunculus/runtime` recover / resume | Yes | Second thrash/budget path |
| `tools/full_auto_driver` `_try_recovery` / post-heal | Yes | Driver-only reclaim or identical tweak |

**Done means for P11:** Written census table in class pack (or test) listing every recovered/accounting site; each ✅ through the entrypoint or explicit DENY/exception row. Zero silent bypasses.

### 1d. Identical / budget policy (single choices — no dual-path)

| Topic | Law |
|-------|-----|
| Recovered → identical | **Do not mirror** (P1). Escalate / fail paths still record. |
| Recovered → recovery attempt budget | **Do not count** toward exhaust (P2). Log row may still exist for audit. |
| Pre-heal identical×N after true progress | **Clear that signature on predicate flip** (P3 default) — not left sitting at ×2 |
| False recovered | Still **impossible** via HC-HEAL-SUCCESS — do not weaken gate to “save budget.” |
| Unstick | **Never** zero identical (keep RC6). |

### 2. Mandatory residual closure (all ✅ or named exception table)

| ID | Work | Done means |
|----|------|------------|
| P1 | R12c recovered | No identical bump on recovered; escalate still mirrors |
| P2 | Recovery attempt budget | Recovered rows excluded from `attempt_count` fuel |
| **P3** | **Predicate-progress reclaim** | **Ship** clear/epoch that signature on token flip **or** named exception in `decisions.md` — **not** “deferred / fuzzy / later” |
| P4 | Sticky | Assert recovered alone does not clear sticky; sealed/token still do |
| P5 | Resume / Complete-before | Census pipeline + runtime recovered resume; admit pin without nested recover storm (or named exception) |
| P6 | Dual invoke laws | Census `count_identity` + `count_attempts`; both honest after success or exception row explaining why one untouched |
| P7 | Transient budget=3 | Recovered×N does not alone drive structural identical halt |
| P8 | Mode parity | Partial = Full-auto accounting; no Partial-only wipe (`FULL_AUTO_REGRESSION_RISK` = no) |
| P9 | Unstick RC6 | Explicit test: unstick does not zero identical |
| P10 | E2E matrix | recover once → N starts same fp → prove no thrash-from-success; fail path still halts |
| **P11** | **Caller census** | Every recovered/accounting site → one entrypoint; census table ✅; **no silent second path** |

### 3. Exception tables (empty-by-default or named)

| Table | Purpose |
|-------|---------|
| `POST_HEAL_EPOCH_ALLOW` | Narrow allow for identity epoch on predicate flip (if needed beyond default clear) |
| `POST_HEAL_ATTEMPT_COUNT_RECOVERED` | Default **false** — recovered never fuels; allowlist only if proven need |
| Dual-cap exception notes | If P6 leaves one counter untouched, one line why in decisions |
| **P3 exception (only if not shipping reclaim)** | Mandatory paragraph in `decisions.md` — why pre-heal ×N may remain |
| **P11 DENY / bypass rows** | Any caller that must not go through the entrypoint — named, tested, rare |

### 4. Cousin plug-in (must say in implement notes)

| Cousin | Plug |
|--------|------|
| HC-HEAL-SUCCESS | Do not reopen false recovered |
| BUD-1 / DP-BUD1 | Product reclaim stays; this class adds success≠fuel + **predicate-progress reclaim (P3)** |
| Done / Admit / Pin | No rewrite; consume their honesty |
| All four prior clinic classes | Fewer storms after their fixes |

### 5. Tests (`MUX_FORENSICS=0`) — mandatory for B+

- Adapted R12c: recovered no bump; escalate bumps  
- attempt_count: recovered then escalate → budget uses fail, not success  
- **P3:** pre-heal identical×2 + recovered + predicate flip → signature cleared (or skip only if named exception logged)  
- **P3 anti-C:** recovered alone does **not** clear / stamp epoch  
- finalize_heal_success does not alone stamp epoch  
- **P11:** census / import-guard style — recovered accounting only via entrypoint  
- P9 unstick identical stable  
- P10 e2e same-fp storm matrix  
- Sticky unchanged on recovered + unsealed pin  
- BUD-1 fingerprint reclaim still green  

**Pros:** Closes the last heal-clinic class thoroughly; P3+P11 remove the “thin A under B+ label” footgun.  
**Cons:** Largest Wave 2; R12c rewrite; predicate reclaim must not become epoch-on-every-recover.

**Real-world worst case if B+ is wrong:** Epoch on recovered alone → infinite retry (C); **or** ship P1 only and leave pre-heal ×2 → next fail still ×3; **or** helper exists but driver/pipeline bypass (P11 miss) → max_invokes still kills Partial.

| Axis | Assessment |
|------|------------|
| Partial certainty | High if P1–P11 closed (esp. P3 + P11) |
| All-modes / Full-auto | Same law |
| Cousin closure | High (campaign complete after L3) |
| Complexity left | Low if P3 choice + P11 census honest |
| What you give up | Calendar / implement size |
| Implement cost | High |
| Regression risk | Medium–high (R12c + predicate clear) — matrix required |
| Reversibility | Medium |
| FULL_AUTO_REGRESSION_RISK | **no** — forbid Partial-only soft clear |

---

## Option C — Alternate: epoch on every recovered

**What we would do:** After every `status=recovered`, call `stamp_budget_epoch` (and maybe clear failed memo) so max_invokes always resets.

**Pros:** Simple “always get another try.”  
**Cons:** Hides stuck holes; fights identical×3; can burn GPU forever on same fingerprint; conflicts with BUD-1 “only on product change” doctrine.

**Real-world worst case:** Mohan Partial loops forever on one incomplete producer with fresh invoke budget each “heal.”

| Axis | Assessment |
|------|------------|
| Partial certainty | Low (false progress) |
| All-modes | Dangerous shared |
| Cousin closure | Negative (reopens thrash) |
| FULL_AUTO_REGRESSION_RISK | yes — unattended burn |

**Tests:** Would need hard “same predicate → still halt” guards — essentially inventing B+ the hard way.

---

## Option Defer

**What we would wait for:** Live Partial soak after heal_validate L3; named Debug if a specific stage dominates; more HEAD map on P5 Complete-before.

**Risk if we wait:** Same-fp thrash after honest recover still burns unattended runs; clinic Wave 1 otherwise complete.

---

## Recommendation (not a decision)

- Preferred: Option **B+** (tightened: **P3 ship predicate reclaim by default**; **P11 caller census mandatory**)
- Why for **error-free Partial:** Honest recover that still spends identical/budget is the last clinic poison; P1-alone leaves pre-heal ×2 → next fail ×3; multi-caller bypass reopens max_invokes.
- Why **all modes:** Same accounting law; no Partial-only wipe.
- Honest downside: Bigger implement; must not turn “success ≠ fuel” into “success = free infinite retry” (that’s C).
- Devil’s-advocate: Pick **A** for a one-evening patch if you only care about identical×N after recover and accept max_invokes + stuck ×2 residual. Pick **C** only if you explicitly want retry-at-all-costs (not recommended). Pick **Defer** only if you want soak evidence before touching R12c.

---

## Cousins to investigate next (suggestions)

| Class id | Why related | Bigger shared SSOT? |
|----------|-------------|---------------------|
| heal_validate_stage_fail | False recovered closed; leftover = this accounting | yes — HC-HEAL-SUCCESS stays; HC-POST-HEAL-BUDGET plugs in |
| hollow_pass | Fake done → re-enter → budget burn | yes — Done honesty feeds fewer re-enters |
| leapfrog_resume / wrong_pin | Wrong land → sticky + identical storms | yes — Admit/Pin already shipped |
| _(none left in clinic queue)_ | After this L3 → Wave 3 `/heal-clinic-readiness` | — |

Update [`../../cross_class_patterns.md`](../../cross_class_patterns.md): HC-POST-HEAL-BUDGET → `options_open`.

---

## Evidence appendix

- HEAD code (**SSOT**): `recovery_controller.py` R12c / attempt_count; `identical_failures.py` BUD-1 reclaim; `heal_success.py` finalize; `thrash_hardening.py` sticky; `delivery_unstick.py` RC6; `homunculus/budget.py` + `ledger.py` epochs; L1 [`possibility.md`](possibility.md)
- Docs / Partial Zero (**hints**): BUDGET_THRASH / DP-BUD1 A closed; STEP_OFF soak residual “same fp thrash” → this class — verify-or-drop; no `exec_*` browse
- Named exec HINT: none this turn
- Swarm: merge-captain packet (this file); raw optional under `solution_swarm/`

---

## Your verdict (operator fills)

- choice: **B+**
- notes: P3=ship predicate-progress reclaim (not defer); P11=mandatory caller census; P1–P11 complete Post-Heal Accounting
- date: 2026-09-22

## YOUR NEXT ACTIONS

1. L3 done — all five clinic classes implemented.
2. Paste Wave 3 readiness (below).

```
/heal-clinic-readiness
Follow .cursor/skills/heal-clinic/SKILL.md
Write heal_readiness.md. No patches.
```
