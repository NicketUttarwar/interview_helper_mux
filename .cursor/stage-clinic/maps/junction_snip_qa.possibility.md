# Possibility Map — junction_snip_qa

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: llm_full | primary: junction_snip_qa.json + seam_autopsy | seed #65
- module: `junction_snip_qa.run_junction_snip_qa`
- mode default **advisory** but critical incomplete cuts still block — naming trap
- thrash: PRIMARY with mix | max_remaster_rounds=2 | tests: solid

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| edl missing | skip / terminal autopsy fallback | IN_CODE | |
| assembly missing + recut-precedes | Allow (EDL-only ladder) | IN_CODE | `_check_junction_snip_qa` |
| assembly missing + mix done path | Require assembly | IN_CODE | |
| mode off | skipped report early return | IN_CODE | |
| hollow commitment≠live assembly | `_junction_commitment_incompleteness` | IN_CODE | |
| selection hard in contract | `_check` does not require selection artifact | CODE_DOC_CONFLICT | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| assembly mtime < EDL | Remaster | IN_CODE | |
| terminal autopsy | Content identity not mtime-only | IN_CODE | `_persist_terminal_autopsy` |
| stale incomplete residuals | clear_stale_incomplete_cut_residuals | IN_CODE | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| critical incomplete after budget | needs_operator / hard block | IN_CODE | e2e_soft does NOT soften |
| g_listen after remaster | HX-5 pending | IN_CODE | |
| default mode advisory | Still authoritative on criticals | CODE_DOC_CONFLICT | naming |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| success | commitment committed; feel pass/soft; no critical incomplete | IN_CODE | |
| heal | apply_junction_repairs / thought_complete_recut / fuse ladder | IN_CODE | |
| remaster | `_budgeted_remaster_mix` ≤2 | IN_CODE | |
| oscillation | note_junction_oscillation_halt identical applied_sig | IN_CODE | |
| hard | remaster refuse; order_lock; commitment remaster refused | IN_CODE | |
| feel LLM remux_suggested | May remaster | IN_CODE | |
| identical mix⇄junction | incomplete_cut_unresolved | IN_CODE | |

### mix↔junction thrash map (IN_CODE)

1. Mix `refuse_mix_if_live_incomplete_cuts` → pin junction
2. Seed/agenda/runtime: if `junction_recut_precedes_mix` → junction before mix
3. Junction repairs + remasters (inner flag skips mix refuse)
4. Terminal still hard-blocks critical incomplete residuals
5. Oscillation / budget exhaust → needs_operator (no e2e soft for criticals)
6. Remaster → `_set_g_listen_pending_after_remaster`

## 5. Side effects

- QA JSON, thought_complete, feel_audit, seam_autopsy, render_ledger, failure_review, remediation_*, placement_adjustments, live EDL, mix remaster — `IN_CODE`
- Dual ALLOW seam_autopsy: junction + master_finalize — `IN_CODE`

## 6. Complexity traps

- advisory mode label vs blocking criticals — `IN_CODE`
- Feel LLM variance → remaster — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard selection | Not in `_check` | CODE_DOC_CONFLICT |
| assembly soft | Soft only when recut-precedes | CODE_DOC_CONFLICT |
| consumers mix+finalize | Correct | IN_CODE |
| invalidates [] | Remaster clears via profiles | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| thought_complete / feel ≤2 | Soft path or remaster | IN_CODE | |
| feel fail | remux_suggested / remaster / soft_pass paths | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Happy post-mix | Snip ≤2 remasters → commitment → finalize | IN_CODE | |
| Pre-mix recut | Junction-first then mix | IN_CODE | |
| budget/osc halt | needs_operator — **human** | IN_CODE | FULL_AUTO_REGRESSION_RISK |
| g_listen after remaster | Finalize blocked until clear (mode=block) | IN_CODE | FULL_AUTO_REGRESSION_RISK |
| e2e_soft | Does not soften incomplete cuts | IN_CODE | CFG-01 |
| human stall? | Yes on budget/osc/g_listen | IN_CODE | |
| GUI-only? | g_listen; defect review | IN_CODE | |
| partial-only fix risk | Softening criticals for Full-auto weakens ship bar | | yes |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| v2.junction_snip_qa.mode | advisory | Naming trap |
| max_remaster_rounds | 2 | Cap |
| feel_audit_enabled | true | LLM feel |
| thought_complete_llm_enabled | true | LLM recut |
| apply_repairs | true | Auto repair |
| seam_autopsy.commitment_blocks_finalize | true | Finalize hard |
| timeout | 360 | |

## TEST_GAP

- Document advisory vs authoritative semantics
- Full-auto needs_operator exhaustion path without driver

## DoD threats

- [x] 1–7 (thrash, honesty, stalls, OpenAI feel, defaults, ship, cross-stage)

## Open questions

1. Rename default mode to authoritative?
2. Full-auto: classified remediation vs needs_operator on osc?

## discovery_status

`complete`
