# Options packet — leapfrog_resume

status: decided  
verdict: B+  
class_plain_name: Leapfrog resume  
brain: 0.2.0 | code_is_king: true  
revised: 2026-09-22 — operator asked: make B more complete / cousins / widespread?  
decided: 2026-09-22 — VERDICT=B+ (see decisions.md)

## TL;DR (read this first — simple language)

- Plain **B** is the right *shape* (one admit gate + schedule), and it correctly **builds on wrong_pin E**.
- It is **not complete enough** as first written: it under-specifies cousins (especially **hollow done** lying about “ready”), under-specifies a **full caller census**, and does not yet merge pin+leapfrog into one **Admit Constitution**.
- **Agent recommendation:** Option **B+** (complete B) — same API idea, but with cousin closure, honest `producer_ready`, full `from_stage` census, and one shared constitution with wrong_pin E.
- What that gives up: Larger Wave 2 than thin B; hollow_pass / budget get **analysis hooks** in the same change (or explicit follow-on class answers in the same batch).

## What’s missing from plain B (honest gaps)

| Gap | Why it matters | B+ fix |
|-----|----------------|--------|
| Hollow “producer ready” | MUST_PRECEDE uses `producer_ready` / `seed_stage_complete` — hollow done → leapfrog looks legal | Require Done Authority / primary-artifact honesty in ready checks (cousin **hollow_pass**) |
| Loose E allowlist | Specialty heals can skip full order walk | Admit always **clamp**; loose checklist ≠ skip clamp |
| Schedule only “wire checklist” | Vague; agenda has many entry points | Concrete: filter_delivery_candidates + reinject + runner enqueue all call admit/schedule API |
| No caller census | Remutate/recovery/driver still raw `from_stage` | Mandatory census table + lint/test that new writes go through admit |
| Cousins only named | Budget / validate not in scope of implement | Cousin inventory below; B+ either closes shared root or opens their options same day |
| Two patterns (PIN-NAV + LEAP-ADMIT) | Risk of two SSOTs again | Merge into one **Admit Constitution** doc + one module surface |

## Options at a glance

| Option | One-line idea | Best if you want… | Worst trade-off |
|--------|---------------|-------------------|-----------------|
| A — Surgical | Clamp missing sites + tighten E loose | Fast | Incomplete |
| B — Admit gate (thin) | admit_resume + schedule checklist | Core leapfrog only | Leaves hollow/census gaps |
| **B+ — Complete admit constitution** *(recommended)* | Thin B + hollow-honest ready + full census + cousin batch + merge with wrong_pin E | Comprehensive, widespread | Bigger PR / multi-class |
| C — Hard refuse clamp | Never auto-land on hole | Max stop-honesty | Low finish rate |
| Defer | Soak first | Evidence | Schedule leapfrogs hide |

---

## Option A — Surgical

(Unchanged spirit.) Patch clamp call sites + E loose path. **Not enough** for your “complete” bar.

---

## Option B — Bigger deterministic (thin)

Original B: `admit_resume` = clamp → authority → return; wire schedule checklist; HAU exception table; matrix.

**Enough for leapfrog-only.** **Not enough** if you want cousins + widespread honesty in one go.

---

## Option B+ — Complete admit constitution *(recommended)*

**What we would do** (builds on wrong_pin E + thin B):

### 1. One Admit Constitution (widespread SSOT)

Single host story (name flexible — e.g. extend `heal_pin_authority` or `delivery_guardrails`):

```
propose pin (existing navigators)
  → clamp_resume_through_order   # never leapfrog
  → wrong_pin E allowlist+checklist  # never random rewrite
  → admit_resume / admit_schedule    # only API for from_stage + enqueue
```

- **Heal path:** `resolve_heal_from_stage` / `heal_navigate` must end in admit (clamp non-optional even for “loose” allow ids).
- **Schedule path:** `stage_minimum_run_checklist` / `admit_schedule` on agenda filter, reinject, and runner enqueue.
- **HAU exceptions:** one explicit table (speech-first mix beds) next to `MUST_PRECEDE` — not scattered `if`s.

### 2. Honest “ready” (cousin hollow_pass — shared root)

- `producer_ready` / seed-complete used by MUST_PRECEDE must not treat **hollow** `.stage_done` as ready (Done Authority / primary artifact).
- If full hollow_pass class isn’t decided yet: **minimum** — VO clamp chain stages (`layup`, `transitions`, `SDP`, `adjudicate`, `synth`) refuse ready-without-primary.
- Opens or advances **hollow_pass** options in the same campaign turn (you still verdict that class).

### 3. Full `from_stage` caller census (completeness)

Ship a markdown census in the class pack (and a test that greps or lists known allowlisted call sites):

| Family of callers | Examples (HEAD) | Must use admit |
|-------------------|-----------------|----------------|
| Heal navigate / authority | `heal_navigate`, `resolve_heal_from_stage` | yes |
| Premature cap / execute | `resolve_premature_cap_pin`, JobRunner | yes |
| Agenda / filter | reinject, `filter_delivery_candidates` | yes |
| Remutate | `edl_narrative_remutate`, listen_delight remutate | yes |
| Recovery | `recovery_controller`, delivery_unstick | yes |
| Driver | full_auto_driver heal pins | yes |

No new raw `from_stage=` without admit (thin lint or ownership-style checklist row).

### 4. Cousin inventory (thorough list)

| Cousin | Clinic class / family | How B+ addresses it |
|--------|----------------------|---------------------|
| Wrong pin / multi-navigator | **wrong_pin** (E done) | Reuse authority; clamp always on admit |
| Layup→adjudicate→synth order | VO_LADDER / LAYUP-ADJ | MUST_PRECEDE + clamp inside admit |
| Schedule past hole | leapfrog (this class) | admit_schedule |
| Hollow done → fake ready | **hollow_pass** | Honest producer_ready |
| Heal validate ≠ stage | **heal_validate_stage_fail** | Validate must call same ready/admit (follow-on options; don’t soft-pass) |
| Budget thrash after “ok” | **post_heal_budget_thrash** | Fewer leapfrog→identical storms; fingerprint reclaim stays that class |
| Premature_cap ranking residual | PIN residual | Cap goes through admit |
| path_to_master vs order | PIN/seat residual | path only after admit |
| Sealed consumer heal | End-E / Done Authority | Checklist sealed_consumer (already in E) |
| Nested synth / VO ladder | VO cousins | Clamp + vo_ladder (existing) still required |

**Widespread better idea (optional same Wave 2 or immediate next):** treat B+ as campaign doctrine — remaining three classes (**hollow_pass**, **heal_validate_stage_fail**, **post_heal_budget_thrash**) get `/heal-clinic-options` in parallel, each option packet required to say how it plugs into Admit Constitution (not a second SSOT).

### 5. Tests (`MUX_FORENSICS=0`)

- admit == clamp(authority(propose)) for allowlisted + non-allowlisted cases  
- agenda cannot enqueue consumer while MUST_PRECEDE hole open  
- hollow mark_done on adjudicate → synth not admitted  
- remutate/recovery sample call sites use admit  
- Partial and Full-auto same admit results  
- HAU speech-first exception matrix  

**Pros:** Most complete deterministic host story; integrates E; attacks cousins at shared roots.  
**Cons:** Biggest Wave 2; needs your verdicts if hollow_pass changes expand mid-implement.

**Real-world worst case:** Large PR regresses one HAU path — mitigate with exception table + matrix before soak.

| Axis | Assessment |
|------|------------|
| Partial certainty | **Highest** |
| All-modes | **Highest** |
| Cousin closure | **High** (shared roots) |
| Complexity left | Lowest long-term |
| Implement cost | Highest |
| FULL_AUTO_REGRESSION_RISK | no if shared |

---

## Option C — Hard refuse clamp

(Unchanged.) Usually worse for unattended Partial than B+.

---

## Option Defer

Soak after E only. Reasonable only if you accept schedule leapfrogs may still burn ML until B+.

---

## Recommendation (not a decision)

- Preferred: Option **B+**
- Why: You already liked B’s integration with wrong_pin E; B+ is the **complete** version — constitution + hollow-honest ready + census + cousin map.
- If you want smaller: verdict **B** (thin) now, then immediately `/heal-clinic-next` on **hollow_pass** before implement — but you asked for more complete, so **B+** fits better.
- Devil’s-advocate: B+ can sprawl — if so, verdict `custom:B+ phase1=admit+schedule+clamp-on-E; phase2=hollow ready` with two implement pastes.

## Your verdict (operator fills)

- choice: **B+**
- notes: Complete Admit Constitution — integrate wrong_pin E, clamp always, schedule admit, honest ready, census, cousins
- date: 2026-09-22

## YOUR NEXT ACTIONS

1. Prefer **B+** if you want the comprehensive bar.
2. Paste:

```
/heal-clinic-answer CLASS=leapfrog_resume VERDICT=B+
Follow .cursor/skills/heal-clinic/SKILL.md
```

Or thin B: `VERDICT=B` · or phased: `VERDICT=custom:B+ phase1 admit+schedule; phase2 hollow-ready`

3. Do **not** implement until answered.
