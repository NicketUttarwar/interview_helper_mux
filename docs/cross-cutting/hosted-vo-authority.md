# Hosted VO / orientation authority (Cluster C)

**Canon for keep/omit/seat/floor** of hosted synthetic VO and episode orientation.
Implementation: [`src/interview_mux/hosted_vo_authority.py`](../../src/interview_mux/hosted_vo_authority.py).

## Why hosted VO count goes low

| Cause | What happens |
|-------|----------------|
| `never_minted` | Compose/layup hollow or heal pinned a consumer |
| `stripped_last_seat` | `native_open_self_orients` omitted the only synth seat |
| `soft_omit_wipe` | Air-script / omit stamps skipped contentful lines. **Pre-synth process omit is illegal** when it would leave `active < need` — see `may_soft_omit_hosted_line` |
| `cta_anchor_lost` | CTA prune dropped natives that anchored floor lines |
| `freeze_pool_empty` | Hard freeze forbids invent; revive pool empty |
| `counter_skew` | Gap vs EDL counts disagree |
| `edl_survivor_wipe` | Stacking after orientation dropped layups |
| `books_disagree` | Gap omit vs EDL/WAV seat |

## Identify (first-class signal)

`identify_hosted_vo_floor(ctx) → FloorIdentity`

| Status | Rule |
|--------|------|
| `UNWARRANTED` | Not hosted G-Framing Yes |
| `WAIVED` | G1 skip / sticky waive |
| `MET` | `have >= need` |
| `PARTIAL` | `1 <= have < need` — **advisory** (never blocks master) |
| `HOLLOW_ZERO` | warranted and `have < 1` — **advisory** (never blocks master) |

`need` defaults to **3** (`analysis.gap_fill.min_synthetic_vo_lines`) — a **target**, not a ship gate. Persisted on `run_meta.hosted_vo_floor_identity`. Under-floor still stamps floor advisories / action_trace so the miss is visible; only loud playability-block for this count floor is removed. Other playability blockers (e.g. `hosted_vo_wav_coverage`, missing master) are unchanged.

## Disposition priority (orientation)

1. **HEARD_KEEP** — WAV or EDL `vo_pickup` already seats orientation. `force_remint` only when gap still omits/lacks the live line; already-required live gap text → no remint thrash.  
2. **HOLLOW_MINT** — hosted Yes and synth seats hollow  
3. **OPERATOR_OMIT** — durable meta omit, no heard, not hollow  
4. **NATIVE_OMIT** — native open already orients  
5. **KEEP_REQUIRED** — otherwise keep/mint  

Intentional omit must clear EDL + WAV + seats atomically. Heard artifacts always beat gap omit.

## Soft-omit gate (pre-synth)

`may_soft_omit_hosted_line(ctx, line, *, gap_report, reason_code) → bool`

- **False** ⇒ callers must not set `skipped_optional` / `air_script_omit` for process reasons (`air_script_omit_sync`, `rendered_floor_prefer_wav`, `skip_omit_unseat`, …) on contentful hosted synth lines when omitting would leave `active_after < need` and `vo_synthesize` is not done.
- Durable policy / omit-wins (CTA, `execution_contract_waive`) still allow omit.
- Post-synth: gate returns True; WAV clamp / omit-ledger use their own rendered-floor rules.
- Wire every stamper (Pass B filter, air_contract E1/E4, `mark_gap_line_not_on_air`, drift repair, omit ledger) through this helper — do not re-implement hollow-only (`active < 1`) band-aids.

## Rank-to-budget adopt (under-floor publish)

`vo_budget_bands` → `(need, ideal, max)`. `score_hosted_vo_line` / `rank_to_budget_select` / `apply_rank_to_budget_fill`:

- Keep **orientation** always; rank contentful body lines by severity, open TP/nuggets, origin, copy length.
- When layup publish is under `need`, **`publish_layup_plan_to_gap_report`** runs one rank-to-budget adopt (`fill_to="need"`) from a draft-backed pool: live prior ∪ hash-fresh `gap_report.draft.json` ∪ plan rows with recoverable text. Adopted lines re-home to `nugget_layup` (no invent). Prefer-native plan skips are soft under fill and may clear when a ranked prior lands on that target.
- Draft lines are ignored when `selection_order_content_hash` disagrees with current selection (stale after reorder).
- Single adopt per selection hash (anti-thrash); still under need → advisory continue and publish best-effort body.
- Soft-omit / process prune must not peel below `need` pre-synth when lines exist; under-floor count never hard-stops the run.

## Floor / heal

- Single `have()` / `need()` — no divergent counters for policy.
- `escalation_should_block` is always false for hosted VO count-floor PARTIAL/HOLLOW_ZERO.
- Escalations are derived: `reconcile_escalations` triple-clears operator JSON + run_meta + plan `_meta` when `have >= 1`.
- On **MET**, also clears stale hollow-era `floor_aspirational_proceeded` / `aspirational_proceeded` and `floor_advisories` rows for `hosted_vo_floor` with `have < need`. `floor_snapshot(persist=True)` invokes reconcile so evaluate paths self-heal.
- Heal pin for hollow / no-synthesize → `nugget_layup_compose` or `gap_framing_compose` only (never `edl_narrative_audit`).

## EDL survivors after orientation

`EDL_SURVIVORS_AFTER_ORIENTATION`: orientation, `nugget_layup`, and `required` before-lines must remain seated on **all** segment indices (including open idx==0).

Assembly consults ``edl_before_line_survives()`` (same module) — do not re-hardcode the filter in ``build_flow1_edl``. Survivor-class WAV-without-EDL is published as ``edl_survivor_wipe`` (error_class ``vo_audibility_drift``) and heals via EDL rebuild, not remint.

## Related

- [publishability-contract.md](publishability-contract.md) T0-4  
- [nugget-layup-system.md](nugget-layup-system.md) H3 (gap owns air / plan owns ledger — intentional; this module owns keep/omit/seat/floor)  
- End-A seat freeze: disposition apply HEARD/HOLLOW allowlisted; invent reseat forbidden  
