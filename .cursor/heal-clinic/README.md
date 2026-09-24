# Heal Clinic pack

**Campaign SSOT:** [`../plans/heal_clinic.plan.md`](../plans/heal_clinic.plan.md)  
**Skill:** [`../skills/heal-clinic/SKILL.md`](../skills/heal-clinic/SKILL.md)

## What you do (operator)

1. Open a Cursor Agent chat.
2. Paste a command from [`paste_prompts.md`](paste_prompts.md) (start with **`/heal-clinic-next`**).
3. Read the **TL;DR** and **Option A / B / C** in simple language.
4. Pick a verdict (`/heal-clinic-answer`) when you are ready — or ask for more / cousins.
5. Paste **`/heal-clinic-next`** again for the next open class.
6. Only after a verdict: **`/heal-clinic-implement`** for that class.

You stay in control of the cause and the fix size (surgical vs bigger deterministic).

## Waves

| Wave | What | Patches? | Status |
|------|------|----------|--------|
| 0 | This pack + plan + skill | No | complete |
| 1 | Discover + options packets | No | complete |
| 2 | Implement chosen option | Yes (after your verdict) | complete (all five) |
| 3 | [heal_readiness.md](heal_readiness.md) | No | complete (2026-09-22) |

## Classes (independent)

| id | Folder |
|----|--------|
| wrong_pin | [classes/wrong_pin/](classes/wrong_pin/) |
| leapfrog_resume | [classes/leapfrog_resume/](classes/leapfrog_resume/) |
| hollow_pass | [classes/hollow_pass/](classes/hollow_pass/) |
| heal_validate_stage_fail | [classes/heal_validate_stage_fail/](classes/heal_validate_stage_fail/) |
| post_heal_budget_thrash | [classes/post_heal_budget_thrash/](classes/post_heal_budget_thrash/) |

## Index

| File | Purpose |
|------|---------|
| [STEP_OFF.md](STEP_OFF.md) | Live resume + PROGRESS_NOW paste |
| [queue.md](queue.md) | Order for `/heal-clinic-next` |
| [ledger.md](ledger.md) | L1 / options / verdict / L3 status per class |
| [paste_prompts.md](paste_prompts.md) | Copy-paste commands |
| [agent_swarm_protocol.md](agent_swarm_protocol.md) | Subagent roles per class |
| [cross_class_patterns.md](cross_class_patterns.md) | Shared SSOT opportunities (≥2 classes) |
| [heal_readiness.md](heal_readiness.md) | Wave 3 rollup (complete 2026-09-22) |
| [templates/](templates/) | Dossier, map, options packet, decisions |
