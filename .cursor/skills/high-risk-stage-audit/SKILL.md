---
name: high-risk-stage-audit
description: >-
  Paste /high-risk-audit STAGE=… to investigate one high-risk pipeline stage
  for over-engineering and root cause. Opens with a Stage Guide, fills the
  rubric, and ends with an explicit scorecard PASS/FAIL. Optional MODE=fix
  or MODE=rescore after patches.
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

| Mode | Paste |
|------|--------|
| Investigate only (default) | `STAGE=___` |
| Investigate + apply subtraction patches | `STAGE=___ MODE=fix` |
| Re-score after patches already landed | `STAGE=___ MODE=rescore` |

```
/high-risk-audit STAGE=___ MODE=fix
Follow .cursor/skills/high-risk-stage-audit/SKILL.md
```

```
/high-risk-audit STAGE=___ MODE=rescore
Follow .cursor/skills/high-risk-stage-audit/SKILL.md
```

Open a **new chat per stage** for parallel work. Same paste, different `STAGE=`.

---

## What the agent must do

1. **Resolve STAGE** from `.cursor/plans/high_risk_error_stages_report.md` Quick index (match seed `#` or stage id).
2. **Open the chat** with a plain-language **§0 Stage Guide** briefing: what it does, main rules, key considerations, what it does not do.
3. Write/update `.cursor/plans/high_risk_stage_audits/<stage_id>.md` (create from `_TEMPLATE.md` if missing). Status: `in_progress` → `complete`.
4. Fill the rubric in order (§0 → §9). Default **investigate only**.
5. **§5 must end with an explicit scorecard verdict: `PASS` or `FAIL`** (see rules below). Also set `Over-engineered?` to `yes` | `partial` | `no`.
6. When complete, **update only this stage’s row** in the report’s `## Audit findings` table (status, over-eng?, verdict/`PASS|FAIL`, link). Do not rewrite other stages’ rows.

### Mode behavior

| Mode | Do |
|------|-----|
| *(default)* | Investigate only. No product patches. Fill §6 subtraction list; mark `needs_you` rows and stop for operator decisions before coding. |
| `MODE=fix` | After §6–§8, ask (or use already-recorded decisions) for every `needs_you` row, then implement unambiguous + decided items. Re-score §5b **and** refresh §6 (mark shipped rows; append new cuts). |
| `MODE=rescore` | Skip full rediscovery if audit exists. Re-read HEAD code for this stage; rewrite **§5b** (post-change scorecard) + verdict PASS/FAIL; **update §6** (see below); refresh findings row. Keep §0–§4 unless clearly stale. |

---

## Doctrine

- **§0 Stage Guide first** — chat briefing + file section before any error scoring.
- **Errors are hints** toward bloated / wrong logic — not the product.
- **Code is king** — HEAD stage body, helpers, contract YAML, ownership. Report predicates = hunt list.
- **One stage per chat.** Touch only that stage’s audit file + findings row.
- **HEAD first.** Optional peek at `ASSETS/executions/exec_13198_*/operator/forensics_errors.json` only to confirm a named predicate — no full exec archaeology.
- **Do not add heal layers** when simplifying. Prefer peel / refuse / move upstream / delete path.

---

## Rubric (file order)

0. **Stage Guide** (required first)  
1. Job statement  
2. Error-hint intake (classify each report predicate)  
3. Code surface map  
4. Business-logic walk  
5. **Over-engineering scorecard** → **PASS or FAIL** (required)  
6. Complexity subtraction list (`unambiguous` | `needs_you`)  
7. Root-cause verdict  
8. Recommended next action (`simplify` | `split_stage` | `move_policy_upstream` | `delete_path` | `leave` | `fix_now`)  
9. Scope fence  

After `MODE=fix` or `MODE=rescore`, rewrite **§5b — Re-score after changes** (same checks + new PASS/FAIL). Keep §5a as baseline if a prior score exists. Also refresh **§6** per the rescore rules below.

---

## §5 Scorecard PASS / FAIL (hard rules)

Score these checks (each answer `yes` / `partial` / `no`, or a count for responsibilities):

| Check | Fail if |
|-------|---------|
| Responsibilities count | count **≥ 3** |
| Dual / competing SSOTs | **yes** |
| Soft-heal / thrash re-admit loops | **yes** |
| Co-producer / unpaid land | **yes** (stage is a non-primary co-writer that thrash-lands) |
| Brittle predicates vs simple rules | **yes** (not merely `partial`) |
| Disproportionate shard/memo/resume | **yes** |
| “Fix everything downstream” behavior | **yes** |

**`Over-engineered?`**

- `yes` — two or more fail-if rows hit, **or** responsibilities ≥ 4  
- `partial` — exactly one hard fail-if, or only `partial` answers with responsibilities = 3  
- `no` — no fail-if rows; responsibilities ≤ 2; no dual SSOT  

**Scorecard verdict**

- **`PASS`** — `Over-engineered?` is `no`  
- **`FAIL`** — `Over-engineered?` is `yes` or `partial`  

Partial is still a **FAIL** for the findings table (operator wants clear go/no-go). Say so in one line: what would flip to PASS.

Findings row `Over-eng?` column: `yes` / `partial` / `no`, and include `PASS` or `FAIL` in the verdict cell.

---

## Complexity subtraction (§6)

- Prefer **≤5 open (unshipped)** concrete cuts, P0 first. Keep shipped history visible.
- Each row: `unambiguous` (agent may ship in `MODE=fix`) or `needs_you` (operator must pick).
- When operator says “pick recommended / build S…”, record decisions on those rows, then implement.
- After shipping, **always** run §5b re-score — do not claim PASS without it.

### §6 on `MODE=rescore` / after `MODE=fix` (required)

1. **Mark shipped** prior rows: set status column or prefix Change with `done:` and note what landed (one short clause). Do not delete history.
2. **Map remaining FAIL fail-if hits** → new open rows (`S{n+1}…`). Each new row must name which scorecard check it clears.
3. **Append** new recommendations; do not silently rewrite old undecided `needs_you` text — add a decision note if the operator already chose.
4. Cap **open** rows at ~5; park extras under a one-line “backlog” note if needed.
5. If scorecard is **PASS**, §6 may be empty of open rows (or only “leave / monitor”).

---

## Resolve STAGE

Quick index columns: `#` | Stage | Tier | Runs hit | Why high-risk  

- Digits → that seed `#`  
- Id → that backtick stage name  
- Ambiguous / missing → list matching Quick index rows and stop  

Paths: template `_TEMPLATE.md` · report `high_risk_error_stages_report.md` · audits `<stage_id>.md`  

See [reference.md](reference.md) for §0 checklist and findings-row format.
