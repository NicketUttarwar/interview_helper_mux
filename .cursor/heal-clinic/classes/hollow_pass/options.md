# Options packet — hollow_pass

status: decided  
verdict: B+  
L3: implemented  
class_plain_name: Hollow pass  
brain: 0.2.0 | code_is_king: true  
revised: 2026-09-22 — operator bar: comprehensive B+ for Partial + Full-auto, all stages, patch every residual hole  
decided: 2026-09-22 — VERDICT=B+ (see decisions.md)  
implemented: 2026-09-22 — Done Constitution R1–R8 (see decisions.md L3 row)

## TL;DR (read this first — simple language)

- What’s going wrong: Stages can look **done / ready** without an honest primary (JSON/WAV). That lie poisons Partial **and** Full-auto, analysis **and** delivery.
- Plain **B** is the right *shape* (Done Constitution) but **not complete enough** for your bar — too many “optional / targeted / either-or” escapes.
- **Agent recommendation:** Option **B+** (complete Done Constitution) — same story as B, but **every residual is mandatory close or named exception**, mode-wide, with full writer + advance censuses and analysis+delivery coverage.
- What that gives up: Largest hollow_pass Wave 2; longer implement; still does **not** retune local ML or rewrite every stage’s creative body — only **done/ready honesty** (orchestration).

---

## Honest scope of “comprehensive”

| In scope for B+ (must close) | Out of scope (not this class) |
|------------------------------|-------------------------------|
| Every write to `.stage_done` | Model quality / MusicGen / MMAudio tuning |
| Every schedule / MUST_PRECEDE / admit / wait-clear that means “ready” | wrong_pin allowlist content (already E) |
| Analysis + delivery stages with disk primaries (XC-HOLLOW-01 matrix) | leapfrog clamp logic (already B+) — B+ *feeds* it honest ready |
| Partial + Full-auto **same** predicates | Soft product success via e2e_soft (already forbidden) |
| Gate marker-only as **explicit exception table** | Heal-validate body vs validate class (cousin — must plug in, not re-own) |

“Patch all holes” = **no silent hollow done/ready path left**. It does **not** mean every stage never fails — failures must be **honest**.

---

## Problem overview (simple language)

### The lie in one picture

```
Real work product missing / thin / refuse-stub
        ↓
.stage_done exists  OR  heal touches / force-stamps marker
        ↓
is_done / seed walk / MUST_PRECEDE / admit says “ready”
        ↓
Partial or Full-auto leapfrogs, thrash, or ships on a hollow foundation
```

### Already mostly fixed (don’t re-litigate)

| Already strong | Meaning |
|----------------|---------|
| `mark_done` + ownership + Done Authority | Normal stamps refuse many hollows |
| Mix seated / finalize PMQ / LLM try_mark_done | Specific ship + LLM hollow closed |
| e2e_soft alone | Does not hollow-stamp quality |
| Leapfrog B+ VO five | VO-chain ready hook only — **not** class close |

### Residuals this class owns — B+ must close **each** row

| # | Residual | B+ mandatory close |
|---|----------|-------------------|
| R1 | Seed-order `Path.touch` restamp | Restamp **only** via `try_mark_done` / `heal_or_refuse_mark`, or only if already `seed_stage_complete` |
| R2 | `_mark_done_raw` heal flush | Raw stamp only after incompleteness None **and** outputs present; else refuse; census every caller |
| R3 | Post-master hole backfill | Written policy: allowlisted stages + outputs required **or** unmark — never silent empty stamp |
| R4 | Ready honesty only on VO five | `producer_ready` honesty for **all** MUST_PRECEDE + all disk-mapped schedule producers |
| R5 | Bare `is_done` advance/skip | Full **advance census**: seed walk, wait-clear, agenda skip, driver “already done” — move to `seed_stage_complete` / `may_clear_wait` |
| R6 | XC-HOLLOW-01 analysis thin | Matrix: every `ANALYSIS_ORDER` + `DELIVERY_ORDER` id with `STAGE_ARTIFACT_DISK_PATHS` (or secondaries) refuses hollow mark / seed-complete |
| R7 | Non–FORCE_DONE_GUARDED producers | Extend incompleteness / force-guard coverage **or** document why stage is marker-only |
| R8 | Mode split | One SSOT — Partial accelerated and Full-auto identical done/ready law (`FULL_AUTO_REGRESSION_RISK` = no) |

---

## Options at a glance

| Option | One-line idea | Best if you want… | Worst trade-off |
|--------|---------------|-------------------|-----------------|
| A — Surgical | Restamp + widen MUST_PRECEDE ready | Fast | Leaves R2–R3, R5–R7 |
| B — Done Constitution (thin) | Writers + ready story, fuzzy “targeted” | Core idea only | Not thorough enough for your bar |
| **B+ — Complete Done Constitution** *(recommended)* | Thin B + mandatory close of R1–R8 + censuses + exception tables + cousin plug-in | Comprehensive Partial + Full-auto | Biggest Wave 2 |
| C — Unmark-only | Never restamp / auto-stamp | Max stop-honesty | Finish rate crash |
| Defer | Soak first | Evidence | Holes stay |

---

## Option A — Surgical

R1 + R4 only. **Not enough** for your thoroughness bar.

---

## Option B — Bigger deterministic (thin)

Original B: Done Constitution idea with optional XC / “targeted” `is_done` / either-or analysis. **Enough for spirit. Not enough if you want all holes closed.**

---

## Option B+ — Complete Done Constitution *(recommended)*

### 1. One law (mode-wide — Partial + Full-auto)

```
WRITE  .stage_done  → only try_mark_done / heal_or_refuse_mark
                       (incompleteness + outputs green; raw only as gated escape)
READ   “ready”      → only seed_stage_complete / producer_ready / may_clear_wait
                       (never bare is_done for advance / schedule / wait-clear)
MODES               → identical predicates (no Partial-only soft stamp)
```

Extend **Done Authority** + **Admit Constitution** — pattern id `HC-HOLLOW-DONE`. No third navigator brand.

### 2. Mandatory residual closure (checklist for implement — all must be ✅ or named exception)

| ID | Work | Done means |
|----|------|------------|
| R1 | Kill bare `Path.touch` restamp | `apply_seed_order_heal` uses Done Authority |
| R2 | Census + gate every `_mark_done_raw` | Pack markdown + lint test; heal path can’t stamp thin |
| R3 | Post-master backfill policy | Code + test: no outputs → no stamp |
| R4 | Widen `producer_ready` | All MUST_PRECEDE (+ disk-mapped producers used by admit/filter) |
| R5 | Advance census | Table of bare `is_done` advance sites → converted or exception-listed |
| R6 | Stage matrix XC-HOLLOW-01 | Parametrize ANALYSIS_ORDER ∪ DELIVERY_ORDER with disk paths: hollow mark → refuse / not seed-complete |
| R7 | Unguarded / thin incompleteness | Force-guard or specialized incompleteness or explicit “gate/marker-only” row |
| R8 | Mode parity tests | Same fixture Partial vs Full-auto → same seed-complete / admit_schedule |

### 3. Exception tables (required — like HAU on leapfrog)

| Table | Purpose |
|-------|---------|
| **GATE_MARKER_ONLY** | Operator gates allowed marker-without-primary (e.g. transcript_review) — listed, tested |
| **POST_MASTER_BACKFILL_ALLOW** | Stages backfill may touch — each requires outputs or is forbidden |
| **RAW_STAMP_ALLOW** | Who may set `_mark_done_raw` — tests + fixtures only unless listed |

No silent exceptions.

### 4. Full censuses (ship in class pack + lint tests)

**Writer census** — every HEAD site that creates/touches `.stage_done` (`mark_done`, `touch`, `_mark_done_raw`, backfill, promote, restamp).

**Advance census** — every HEAD site that skips / clears wait / schedules using bare `is_done` for “already complete.”

Same spirit as leapfrog `from_stage_census.md`.

### 5. Cousin plug-in (same campaign doctrine)

| Cousin | B+ requirement |
|--------|----------------|
| leapfrog_resume | Uses widened `producer_ready` (already Admit) |
| wrong_pin E | Checklist calls seed-complete, not hollow done |
| heal_validate_stage_fail | Options **must** say validate = same seed-complete (open options next; don’t soft-pass) |
| post_heal_budget_thrash | Fewer fake “ok” stamps → less budget burn; options plug into Done Constitution |

### 6. Tests (`MUX_FORENSICS=0`) — thorough matrix

- R1 restamp without primary → not seed-complete  
- R2 raw heal thin doc → refuse  
- R3 backfill without outputs → no stamp / not seed-complete  
- R4 every MUST_PRECEDE producer: marker-only → not ready  
- R5 sampled advance sites: hollow marker does not skip re-invoke  
- R6 parametrize disk-mapped ANALYSIS + DELIVERY stages  
- R8 Partial env vs Full-auto env identical results  
- Census lint: new writers/advance sites must appear in pack tables  
- Gate / backfill / raw exception tables have positive tests (allowed) + negative (unlisted refused)

### Pros / cons / worst case

**Pros:** Matches your “very complete / all modes / all stages / patch the holes” bar; closes family root for validate + budget.  
**Cons:** Largest Wave 2 in Heal Clinic so far; needs careful exception tables so G0 / anti-rewind don’t break.  

**Real-world worst case:** Over-strict matrix blocks a legitimate gate or backfill → night run stops. Mitigate: exception tables + parity tests **before** soak; never Partial-only escape.

| Axis | Assessment |
|------|------------|
| Partial certainty | **Highest** |
| Full-auto / all-modes | **Highest** (shared SSOT) |
| All-stages coverage | **High** for done/ready; stage *body* quality out of scope |
| Cousin closure | **High** |
| Implement cost | Highest |
| FULL_AUTO_REGRESSION_RISK | **no** if shared |

---

## Option C — Unmark-only

Max honesty, lower finish. Usually worse for unattended Partial than B+.

---

## Option Defer

Only if you accept hollow side doors until soak proves otherwise — conflicts with your thoroughness ask.

---

## Recommendation (not a decision)

- Preferred: Option **B+**
- Why: You asked for comprehensive Partial + Full-auto + all stages + patch remaining gaps. Thin B leaves either-ors; B+ makes R1–R8 **mandatory** with censuses and exception tables.
- What “complete” still does **not** mean: rewriting stage creativity or local ML — only **honest done/ready**.
- Devil’s-advocate: If Wave 2 must ship in one evening, verdict `custom:B+ phase1=R1+R4+R8; phase2=R2+R3+R5+R6+R7` — still B+, just sequenced. Do **not** verdict plain B if you want this bar.

---

## Cousins to investigate next

| Class id | Why | Shared SSOT? |
|----------|-----|--------------|
| heal_validate_stage_fail | Validate must use same seed-complete | yes |
| post_heal_budget_thrash | Fake success → budget burn | yes |
| leapfrog / wrong_pin | Already implemented — B+ feeds them | already |

---

## Evidence appendix

- [possibility.md](possibility.md) · [dossier.md](dossier.md)
- HEAD: `done_authority.py`, `run_context.mark_done`, `producer_ready`, `apply_seed_order_heal`, `heal_or_refuse_mark`, agenda backfill
- Hints: Partial Zero HOLLOW_DONE partial; XC-HOLLOW-01 OPEN_RISK

---

## Your verdict (operator fills)

- choice: **B+**
- notes: Complete Done Constitution — R1–R8 mandatory; Partial + Full-auto; analysis + delivery; censuses + exception tables
- date: 2026-09-22

## YOUR NEXT ACTIONS

1. Paste `/heal-clinic-next` for heal_validate_stage_fail (must plug into Done Constitution).
2. Optional soak — clinic does not use forensics as proof.

```
/heal-clinic-next
Follow .cursor/skills/heal-clinic/SKILL.md
Read .cursor/heal-clinic/STEP_OFF.md, queue.md, ledger.md.
Pick next open class per skill algorithm. Discover or options as needed.
Simple language. No product patches. End with YOUR NEXT ACTIONS.
```
