# Options packet — wrong_pin

status: decided  
verdict: E  
class_plain_name: Wrong pin  
brain: 0.2.0 | code_is_king: true  
revised: 2026-09-22 — operator asked for more elegant “don’t start wrong pin” options beyond original B  
decided: 2026-09-22 — VERDICT=E (see decisions.md)

## TL;DR (read this first — simple language)

- What’s going wrong: Several heal navigators can still jump the walk to the **wrong stage**. Most pin rewrites are thrash, not recovery.
- What you said you want: **Don’t start that buggy process.** Only heal/repin when prerequisites are real; prefer a **narrow allowlist** / happy-path checklist; pin change rare, not default.
- **Agent recommendation:** Option **E** (Refuse-by-default + prereq checklist + one SSOT pipeline). It is Option B’s determinism, plus “most heals never fire.”
- What that gives up: Some aggressive auto-recovery; stuck runs may stop honestly (`incomplete` / `needs_operator`) instead of thrashing.

## Options at a glance

| Option | One-line idea | Best if you want… | Worst trade-off |
|--------|---------------|-------------------|-----------------|
| A — Surgical | Fix bypasses + parity tests | Fast | Multi-navigator stays |
| B — One pipeline SSOT | Single `resolve_heal_from_stage` | Same pin everywhere | Still heals/repins often |
| C — Disagree detector | Log/assert when navigators disagree | Visibility | Doesn’t stop thrash |
| **D — Happy-path only** | Normal walk never calls heal navigate; checklist gate before any stage | Almost no wrong pins | Recovery when truly broken is manual/slow |
| **E — Refuse-by-default + allowlist + checklist + SSOT** *(recommended)* | Pin rewrite **off** unless allowlisted error **and** prereq checklist green; one pipeline | Prevent thrash at the source | Need a good allowlist |
| **F — Rewind-only** | Heal may only move to earliest incomplete on **current path** — never jump sideways | No cross-tree wrong pins | Can’t jump to true specialty producers without allowlist escape |
| Defer | More map / live Debug | Evidence | Residual stays |

Original A/B/C kept below for comparison. **New elegant options are D / E / F.**

---

## Option A — Surgical (smallest honest fix)

**What we would do:** Parity tests + close known bypasses (`classify_heal_error`, path fall-through) without redesigning heal policy.

**Pros:** Small. **Cons:** Does not match “don’t start this.”  

**Real-world worst case:** Next unlisted bypass still thrash-pins.

---

## Option B — Bigger deterministic (one pipeline only)

**What we would do:** One `resolve_heal_from_stage` all callers use (specialty → token pin → clamp → path-to-master last).

**Pros:** Deterministic *which* pin. **Cons:** Still **starts heal/repin often** — you said most of those starts are unnecessary thrash.

**Real-world worst case:** Elegant wrong answer — always the same wrong jump.

**Why it’s not enough alone for you:** Determinism ≠ prevention. You want the **gate before heal starts**.

---

## Option C — Alternate (inventory + disagree hard-fail)

**What we would do:** Detect navigator disagree; freeze new navigators.

**Pros:** Honesty. **Cons:** Doesn’t raise unattended success odds.

**Real-world worst case:** Noisier Partial without fewer root thrash events.

---

## Option D — Happy-path only (almost no heal navigate)

**What we would do:**

1. **Normal progress** uses only: seed order + `MUST_PRECEDE` + “stage may run?” checklist (artifacts/upstream done/gate state).
2. **`heal_navigate` / premature_cap rewrite default OFF** on Partial and Full-auto product defaults.
3. On failure: mark incomplete / refuse honestly — **do not** invent a new `from_stage`.
4. Optional: operator or explicit allowlisted remediation job to resume (not silent driver thrash).

**Pros:** Wrong pin almost cannot start; matches “shouldn’t happen in the first place.”  
**Cons:** Less self-healing; true recoverable errors need human or a separate tool; Full-auto may stall more until allowlisted remediations exist.

**Real-world worst case:** A soft OpenAI schema miss that used to self-heal now stops the night run until you intervene — higher honesty, lower “keep going” rate until checklists/remediation are good.

| Axis | Assessment |
|------|------------|
| Partial certainty | High against thrash; medium for unattended finish |
| All-modes | Shared if defaults match; else `FULL_AUTO_REGRESSION_RISK` |
| Cousin closure | High for wrong_pin / budget thrash |
| Complexity left | Heal code becomes dead weight unless deleted later |
| Implement cost | Medium–high (call-site disable + checklist) |
| Reversibility | Medium |

---

## Option E — Refuse-by-default + narrow allowlist + prereq checklist + one SSOT *(recommended)*

**What we would do** (elegant combination of B + your intent):

1. **One pipeline** (from B): every heal path calls `resolve_heal_from_stage` only — no parallel navigators.
2. **Refuse-by-default:** proposed pin rewrite is **denied** unless:
   - error class is on a **narrow allowlist** (e.g. G0 pending, voice-ref, high-gap unframed, fuse oscillation, named `premature_complete:<known>`, incomplete_cut→junction — table reviewed by you), **and**
   - **minimum prereq checklist** for that target stage is green (required artifacts exist, upstream producers honestly complete, not a sealed consumer, freeze/ownership allows).
3. If checklist fails: **do not pin elsewhere** — stay / incomplete / needs_operator with a clear reason (“heal refused: missing assembly.wav”).
4. **Happy-path checklist** for the seed walk: stage only scheduled when its own minimum run checklist passes (prevents starting work that will immediately heal-thrash).
5. Pin **change** remains possible — but rare, allowlisted, checklist-gated — not the default reaction to every error string.

**Pros:** Prevents most thrash at the gate; still recovers real known cases; deterministic; works for Partial + all modes with one allowlist.  
**Cons:** Allowlist design is the product decision (too narrow → more stops; too wide → thrash returns). Needs good tests per allowlist row.

**Real-world worst case:** Allowlist misses a legitimate recovery → run stops honestly; you add one allowlist row + checklist after a DP (far better than silent wrong pin).

| Axis | Assessment |
|------|------------|
| Partial certainty | **Highest** among options for “don’t start wrong pin” |
| All-modes / Full-auto | High if same allowlist+checklist (prefer this) |
| Cousin closure | High for wrong_pin; helps leapfrog/budget |
| Complexity left | Medium (one pipeline + tables) |
| What you give up | Free-form “heal anything from error prose” |
| Implement cost | High (worth it) |
| Regression risk | Medium — mitigate with matrix per allowlist id |
| Reversibility | Medium (feature-flag allowlist widen) |
| FULL_AUTO_REGRESSION_RISK | **no** if shared; **yes** if Partial-only refuse |

**Tests (`MUX_FORENSICS=0`):**  
- Allowlisted class + green checklist → expected pin.  
- Allowlisted class + red checklist → refuse, no sideways pin.  
- Non-allowlisted error → refuse rewrite.  
- B1–B3 token laws still hold inside the single pipeline.  
- Happy-path: stage not scheduled without checklist.

---

## Option F — Rewind-only (never jump sideways)

**What we would do:** After any failure, heal may only move to the **earliest incomplete stage on the current MUST_PRECEDE / seed path** — never jump to an unrelated producer from error text. Specialty cases need explicit allowlist escapes (subset of E).

**Pros:** Simple mental model; kills cross-tree wrong pins.  
**Cons:** Alone, cannot express “voice-ref must go to missing_framing” without escapes → tends to become E anyway.

**Real-world worst case:** True specialty hole ignored; walk rewinds uselessly along the path.

---

## Option Defer

Wait for `leapfrog_resume` L1 or a named live Debug of one thrash pin.  

**Risk:** Another Partial soak burns on the same class.

---

## Recommendation (not a decision)

- Preferred: Option **E**
- Why for **error-free Partial:** Stops the buggy process from starting; pin change is rare and proven.
- Why for **all modes:** Same allowlist + checklist + pipeline — no Partial-only soft heal.
- Honest downside: You (operator) own the allowlist contents via verdicts when rows are added.
- Devil’s-advocate: Pick **D** if you want heal almost deleted; pick **B** if you only want one navigator but still aggressive auto-repin; pick **F** if you want the simplest rule and accept allowlist escapes later.

## Cousins to investigate next

| Class id | Why related | Shared with E? |
|----------|-------------|----------------|
| leapfrog_resume | Clamp = part of pipeline after allowlisted pin | yes |
| post_heal_budget_thrash | Refuse rewrite cuts budget burn | yes |
| hollow_pass | Checklist must not treat hollow done as prereq green | yes |
| heal_validate_stage_fail | Validate must use same checklist honesty | yes |

## Evidence appendix

- HEAD multi-navigator census: [possibility.md](possibility.md)
- Operator intent this turn: prevent start; narrow allowlist; checklist; pin change rare

## Your verdict (operator fills)

- choice: **E**
- notes: Refuse-by-default + narrow allowlist + prereq checklist + one SSOT pipeline; prevent wrong-pin thrash at the gate
- date: 2026-09-22

## YOUR NEXT ACTIONS

1. Pick a letter (lean **E** if you agree with refuse-by-default + checklist + SSOT).
2. Paste:

```
/heal-clinic-answer CLASS=wrong_pin VERDICT=E
Follow .cursor/skills/heal-clinic/SKILL.md
```

Optional note after VERDICT, e.g. `VERDICT=E` then in the same message: “allowlist must stay shared across Partial and Full-auto; no silent prose heals.”

3. Only after answer: `/heal-clinic-implement CLASS=wrong_pin` (Wave 2 will flesh allowlist+checklist design before coding).
