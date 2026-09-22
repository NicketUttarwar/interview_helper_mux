# DP-PRE-PARTIAL — Launch Partial or keep digging?

- status: decided (A — launch unlocked)
- created: 2026-09-22T02:00:00Z
- decided: 2026-09-22T02:10:00Z
- blocks: First `partially_accelerated` Mohan proof (0.2.0); companion watch; no forensics
- resume_hook: /partial-companion RUN=<exec_id>
- solution_swarm_agents: 0 (campaign census only)
- aligns_with: batches 1–2 closed; cousin_matrix; phase_scorecard (stale labels)

## TL;DR (read this first)
- What’s wrong (1–2 sentences): Priority batches 1–2 Decision Packets are **all decided and implemented**. The campaign gate is now whether to **launch** Partial proof or spend more cycles on residual families that never got their own DP.
- What you’d notice in Partial: Either a clean companion-watched Mohan walk, or a stop to open **DP-BUD1** / named residuals if soak hits them.
- Why we can’t ignore it for ironclad Partial: Launch without a logged go/no-go violates campaign law; digging forever without a soak also never proves Partial zero.
- Agent recommendation: Option **A** — launch Partial Mohan (0.2.0) with companion watch; **named residuals** are soak-gates (not silent ignore).
- What that recommendation gives up: No preemptive **BUDGET_THRASH** root patch before first live Partial bytes.

## Context (enough to decide)
- Where: Campaign gate between “code families closed” and “Partial proof run.”
- Cousin family: **pre-launch residual inventory** (not a new product root).
- Batches 1–2: closed (mechanism honesty + critical phase blockers including HAU).

### Family board (HEAD)
| Family | Status | Notes |
|--------|--------|-------|
| HOLLOW_DONE | closed | Done Authority |
| MIX_JUNCTION_SEAT | closed | Seat authority + HAU + footguns |
| PIN_PREMATURE | closed | B1–B3+B6 |
| FREEZE_CONSTITUTION | **matrix lag** | A2+A3+A4 implemented; cousin_matrix section text still says “open” — treat **closed for launch** unless soak proves otherwise |
| SDP_CUE_SLOTS | closed | A+ |
| LOCAL_ML_RECLAIM | closed | A |
| VO_LADDER_PARTIAL | closed | VO1 + NESTED + LAYUP |
| ESR_POST_MASTER | closed | C1–C4 |
| SHIP_BAR_VOCAB | closed | C5 |
| BUDGET_THRASH | **open** | DP-BUD1 draft only; often symptom of closed families |

### Named residuals (accept or dig — do not silently fold)
| Residual | Why separate | Launch impact |
|----------|--------------|---------------|
| BUDGET_THRASH / DP-BUD1 | Budget epoch vs identical-failure walk | If Partial spins on max_invokes / i7-class → stop, open DP-BUD1 |
| Premix commitment diverge → `incomplete_cut` | MIX residual; HAU out-of-scope | Possible junction thrash mid-build |
| Dual render files remain | HAU unified admit, not one render pipeline | Preview-era beds need remaster path (landed); soak may still surprise |
| Phase scorecard labels | Still say PARTIAL_BLOCKED | Docs only — refresh after go |

## Options at a glance
| Option | One-line idea | Best if you want… | Worst trade-off |
|--------|---------------|-------------------|-----------------|
| A | Launch Partial Mohan 0.2.0 + companion; residuals = soak gates | Prove Partial now | First soak may open BUD1 |
| B | Dig first: open DP-BUD1 (and/or premix residual) before any Partial | Ironclad budget law first | More calendar before proof |
| C | Launch accepting listed residuals as permanent accepted risk | Explicit risk register | May ship with known thrash classes |
| Defer | Wait; refresh scorecard/matrix only | Doc hygiene | No proof |

## Option A — Launch + companion (recommended)
**What we would do**
1. Operator logs verdict A (notes may list soak-gates).
2. Fresh Partial run: `partially_accelerated`, brain **0.2.0**, **MUX_FORENSICS unset/0**, new `exec_*` (MUX_FRESH=1).
3. Companion skill watches stalls → expected_gate vs new DP; **no forensics**.
4. If BUDGET / premix residual dominates → pause and open that DP (not silent patch).

**Pros:** Campaign goal is proof; closed families need live exercise.  
**Cons:** BUDGET still open as a family.  
**Cousin closure if chosen:** Unlocks proof; CLOSEOUT later.  
**Tests:** None before launch; companion + existing matrix stay green.

## Option B — Dig BUDGET (and optional premix) first
**What we would do:** Present DP-BUD1 (and optionally premix→incomplete_cut packet) before any Partial launch.  
**Pros:** Fewer mid-soak stops.  
**Cons:** BUDGET often symptom; may over-invest.  
**Cousin closure if chosen:** BUDGET_THRASH toward closed-when before proof.

## Option C — Launch with permanent accepted residuals
**What we would do:** Same as A, but NOTES permanently accept BUDGET + premix + dual-render without auto-opening DPs on first hit.  
**Pros:** Clear risk register.  
**Cons:** Weakens “error-free” bar if storms are ignored.

## Option Defer — Docs only
Refresh cousin_matrix FREEZE status + phase_scorecard; no launch.

## Recommendation (not a decision)
- Preferred: **A**
- Why for **error-free Partial**: Proof is the next SSOT; closed code families without soak are speculation. Companion + soak-gate residuals keeps honesty without pretending BUDGET is closed.
- Honest downside: First Partial may stall on budget/identical before product roots.
- Devil’s-advocate: Choose **B** if you would rather not burn a Mohan wall-clock on a known open family.

## Your verdict
- choice: **A** — Launch + companion; soak-gate residuals
- notes: Mohan 0.2.0 Partial; companion; no forensics; soak-gates BUDGET + premix→incomplete_cut + dual-render
- date: 2026-09-22T02:10:00Z
- implemented: n/a (launch unlock)

## YOUR NEXT ACTIONS
Launch unlocked. Start a **fresh** Partial Mohan run, then paste COMPANION_NEXT from STEP_OFF.md with the new `exec_*`.
