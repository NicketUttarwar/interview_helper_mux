---
name: high-risk-stage-audit
description: >-
  Paste /high-risk-audit STAGE=… to investigate one high-risk pipeline stage
  for over-engineering and root cause. Starts with a Stage Guide (what it does,
  rules, considerations), then scores complexity and writes findings.
disable-model-invocation: true
---

# High-risk stage audit

**You paste one line. The agent does the rest.**

## Copy-paste command (only thing the operator needs)

Replace `___` with the stage **seed number** (e.g. `45`) or **stage id** (e.g. `nugget_layup_compose`):

```
/high-risk-audit STAGE=___
Follow .cursor/skills/high-risk-stage-audit/SKILL.md
```

Examples: `STAGE=45` · `STAGE=nugget_layup_compose` · `STAGE=41`

Optional fix mode (only if you want patches in the same chat):

```
/high-risk-audit STAGE=___ MODE=fix
Follow .cursor/skills/high-risk-stage-audit/SKILL.md
```

Open a **new chat per stage** for parallel work. Same paste, different `STAGE=`.

---

## What the agent must do (operator does not run scripts)

1. **Resolve STAGE** from `.cursor/plans/high_risk_error_stages_report.md` Quick index (match seed `#` or stage id).
2. **Open the chat** with a plain-language **§0 Stage Guide** briefing: what the stage does, main rules, key considerations, what it does not do.
3. Write the full investigation into `.cursor/plans/high_risk_stage_audits/<stage_id>.md` (create from `_TEMPLATE.md` if missing). Mark `status: in_progress` → `complete`.
4. Fill the rubric in order (§0 → §8). Default: **investigate only** (no product patches). `MODE=fix` only when the paste says so.
5. When complete, **update only this stage’s row** in the `## Audit findings` table at the bottom of `high_risk_error_stages_report.md` (status, over-eng?, short verdict, link). Do not rewrite other stages’ rows.

## Doctrine

- **§0 Stage Guide first** — chat briefing + file section before any error scoring.
- **Errors are hints** toward bloated / wrong logic — not the product.
- **Code is king** — HEAD stage body, helpers, contract YAML, ownership. Report predicates = hunt list.
- **One stage per chat.** Write that stage’s audit file; touch only that stage’s findings row in the master report.
- **HEAD first.** Optional peek at `ASSETS/executions/exec_13198_*/operator/forensics_errors.json` only to confirm a named predicate — no full exec archaeology.

## Rubric (file order)

0. **Stage Guide** (required first) — functionality, artifacts, rules, considerations, LLM/N/A, non-goals, operator effects  
1. Job statement  
2. Error-hint intake (from report; classify each predicate)  
3. Code surface map  
4. Business-logic walk  
5. Over-engineering scorecard  
6. Complexity subtraction list  
7. Root-cause verdict  
8. Recommended next action (`simplify` | `split_stage` | `move_policy_upstream` | `delete_path` | `leave` | `fix_now`)

Template: `.cursor/plans/high_risk_stage_audits/_TEMPLATE.md`  
Report: `.cursor/plans/high_risk_error_stages_report.md`  
Audits: `.cursor/plans/high_risk_stage_audits/<stage_id>.md`

## Resolve STAGE helper

Quick index columns: `#` | Stage | Tier | Runs hit | Why high-risk  

- If `STAGE` is digits → that seed `#`  
- If `STAGE` is an id → that backtick stage name  
- If ambiguous / missing → list matching Quick index rows and stop for operator pick  

See [reference.md](reference.md) for the §0 checklist.
