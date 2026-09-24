---
name: heal-clinic
description: >-
  Heal Clinic for interview_helper_mux: operator-controlled investigate of five
  heal-variance classes (wrong_pin, leapfrog_resume, hollow_pass,
  heal_validate_stage_fail, post_heal_budget_thrash). Wave 1 discover+options;
  operator picks A/B/C; Wave 2 implement after verdict. Use when operator pastes
  /heal-clinic-* or asks about heal wrong-pin, leapfrog resume, hollow pass,
  heal-validate/stage-fail, or post-heal budget thrash.
disable-model-invocation: true
---

# Heal Clinic

Campaign SSOT: [.cursor/plans/heal_clinic.plan.md](../../plans/heal_clinic.plan.md)  
Pack: [.cursor/heal-clinic/](../../heal-clinic/)  
Paste crib: [reference.md](reference.md) · full pastes: [paste_prompts.md](../../heal-clinic/paste_prompts.md)

**Class ids (only these):** `wrong_pin` · `leapfrog_resume` · `hollow_pass` · `heal_validate_stage_fail` · `post_heal_budget_thrash`

## Operator contract

1. Paste **`/heal-clinic-next`** → one class, thorough work, stop with a ready-to-copy next paste.
2. Operator keeps control of **cause** (L1) and **fix size** (surgical vs bigger deterministic).
3. Options = **A / B / C / Defer** in **simple language**, each with pros/cons, **real-world worst case**, and a **recommendation** (not a decision).
4. Suggest **cousin classes** and cross-class SSOT opportunities.
5. Operator verdict → only then Wave 2 implement.

## Doctrine (non-negotiable)

- **Operator decides.** Recommend only until `/heal-clinic-answer` or a row in `classes/<id>/decisions.md`.
- **Code is king.** Tag claims: `IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN`.
- **Prior `exec_*`:** HINT only if operator **names** a folder; otherwise do **not** browse `ASSETS/executions/`.
- Brain **0.2.0**. Partial lens + **all-modes** impact on every option. Flag `FULL_AUTO_REGRESSION_RISK` if Partial-only.
- Wave 1 = **no product patches**. Wave 2 = `/heal-clinic-implement` only after verdict.
- Product auto-heal ≠ Debug mid-soak doctor ≠ clinic silent patch (**forbidden**).
- No e2e_soft / hollow done / MusicGen stub to fake success.
- Local heavy ML: orchestration honesty only; no model tuning.

## `/heal-clinic-next` algorithm

1. Read `STEP_OFF.md`, `queue.md`, `ledger.md`.
2. Pick **one** class:
   - First ledger row where `L1_map` ≠ `complete`, else
   - First where `L2_options` ≠ `complete`, else
   - First where `verdict` = `awaiting_operator` → **summarize options TL;DR + stop** (do not re-discover; wait for answer), else
   - First where `verdict` is decided and `L3_patch` ≠ `implemented`/`deferred` → remind implement paste + stop, else
   - If all done → say Wave 3 `/heal-clinic-readiness` and stop.
3. Override: if operator named `CLASS=<id>`, use that id.
4. Then run discover or options for that class only (see Commands). Update ledger + STEP_OFF before ending.

## Commands

### Next bug
```
/heal-clinic-next
Follow .cursor/skills/heal-clinic/SKILL.md
Read .cursor/heal-clinic/STEP_OFF.md, queue.md, ledger.md.
Pick next open class per skill algorithm. Discover or options as needed.
Simple language. No product patches. End with YOUR NEXT ACTIONS.
```

### Discover (L1)
```
/heal-clinic-discover CLASS=<id>
Follow .cursor/skills/heal-clinic/SKILL.md
Write classes/<id>/dossier.md + possibility.md from HEAD. No patches.
```

### Options (L2)
```
/heal-clinic-options CLASS=<id>
Follow .cursor/skills/heal-clinic/SKILL.md
Write classes/<id>/options.md — A surgical, B bigger deterministic, C, Defer.
Worst cases + recommendation + cousins. Simple language. No patches.
```

### Answer (verdict)
```
/heal-clinic-answer CLASS=<id> VERDICT=A|B|C|Defer|custom:<text>
Follow .cursor/skills/heal-clinic/SKILL.md
Append decisions.md; update ledger + STEP_OFF. Do not implement unless also asked.
```

### Suggest cousins
```
/heal-clinic-suggest-cousins CLASS=<id>
Follow .cursor/skills/heal-clinic/SKILL.md
Update cross_class_patterns.md if ≥2 classes share a root. No patches.
```

### Implement (Wave 2 only)
```
/heal-clinic-implement CLASS=<id>
Wave 2 explicit. Follow .cursor/skills/heal-clinic/SKILL.md
Patch chosen option only. MUX_FORENSICS=0 tests. Update ledger L3.
```

### Continue
```
/heal-clinic-continue CLASS=<id> LAYER=L1|options|L3
My notes (optional): ...
```

### Readiness (Wave 3)
```
/heal-clinic-readiness
Follow .cursor/skills/heal-clinic/SKILL.md
Write heal_readiness.md. No patches.
```

## Layer stop rules

| Layer | May write | Must not |
|-------|-----------|----------|
| `/heal-clinic-next` | one class map or options; ledger; STEP_OFF | patch; skip awaiting verdict |
| L1 discover | `classes/<id>/dossier.md`, `possibility.md`, ledger L1 | `options.md` as final decision; product code |
| L2 options | `options.md`, `solution_swarm/*`, ledger L2, cross_class hints | product code; single-option packets |
| answer | `decisions.md`, ledger verdict, STEP_OFF | product code unless implement also pasted |
| L3 implement | product + tests per verdict; ledger L3 | implement without verdict; expand discover scope; fresh forensics |
| Wave 3 | `heal_readiness.md` | product code; unprompted exec archaeology |

**Refuse `/heal-clinic-implement`** unless: Wave 2 intent explicit **and** `options.md` exists **and** verdict is logged in `decisions.md` or this turn’s `/heal-clinic-answer`.

## Discover evidence order (every L1)

1. Plain-language card on dossier  
2. Mechanism census — callers of pin / resume / mark_done / validate / budget for this class  
3. Declared SSOT vs actual callers (`IN_CODE` tags)  
4. Closed-vs-residual vs cousin_matrix / prior DPs (**verify on HEAD**)  
5. Partial vs Full-auto / all-modes split  
6. OpenAI-assisted heal paths vs deterministic host rules  
7. Tests + TEST_GAP (`MUX_FORENSICS=0`; no local-ML deep dive)  
8. Write/update `possibility.md` matrices + plain-language summary  

L1 complete only when census table + permutations + residual table + TEST_GAP exist (N/A with reason OK).

## Option packet rules (non-negotiable)

From [templates/options_packet.md](../../heal-clinic/templates/options_packet.md):

- **A** = surgical (smallest honest fix) when possible  
- **B** = bigger deterministic SSOT / family root when possible (or explain why not real)  
- **C** = real alternate (CUT / refuse / gate / second approach)  
- **Defer** = always offered  
- Each: pros, cons, **real-world worst case**, Partial + all-modes, tests  
- TL;DR + **recommendation** + what it gives up + **cousins to open next**  
- Simple language first; code pointers in appendix  

## Subagents

See [agent_swarm_protocol.md](../../heal-clinic/agent_swarm_protocol.md). No agent-count budget. For options: census / surgical / SSOT / alternate / devil’s advocate / tests / cousin scout → **one merge** into `options.md` before stopping.

## Ledger + STEP_OFF (every turn that advances work)

Update [`.cursor/heal-clinic/ledger.md`](../../heal-clinic/ledger.md) columns for the class: `L1_map`, `L2_options`, `verdict`, `L3_patch`, `notes`.  
Update [`.cursor/heal-clinic/STEP_OFF.md`](../../heal-clinic/STEP_OFF.md): `updated`, `campaign_status`, `blocked_on`, `what_you_can_do_now`, decided/open, refresh PROGRESS_NOW paste.

## Verify (L3 only)

- Cascade/matrix pytest with `MUX_FORENSICS=0`
- `./scripts/verify_artifact_contract.sh` if contracts/ownership touched
- No `MUX_FRESH` forensics campaign to prove one class

## End every agent turn with

1. Plain-language status (1–3 sentences)  
2. **YOUR NEXT ACTIONS** (what the operator should paste or decide)  
3. Ready-to-copy next command (`/heal-clinic-next`, `/heal-clinic-answer`, or `/heal-clinic-implement`)
