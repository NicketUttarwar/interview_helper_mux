# Hosted VO / orientation authority (Cluster C)

**Canon for keep/omit/seat/floor** of hosted synthetic VO and episode orientation.
Implementation: [`src/interview_mux/hosted_vo_authority.py`](../../src/interview_mux/hosted_vo_authority.py).

## Why hosted VO count goes low

| Cause | What happens |
|-------|----------------|
| `never_minted` | Compose/layup hollow or heal pinned a consumer |
| `stripped_last_seat` | `native_open_self_orients` omitted the only synth seat |
| `soft_omit_wipe` | Air-script / omit stamps skipped contentful lines |
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
| `PARTIAL` | `1 <= have < need` — aspirational stretch OK |
| `HOLLOW_ZERO` | warranted and `have < 1` — **playability block** |

Persisted on `run_meta.hosted_vo_floor_identity`. Never aspirational-continue on `HOLLOW_ZERO`.

## Disposition priority (orientation)

1. **HEARD_KEEP** — WAV or EDL `vo_pickup` already seats orientation. `force_remint` only when gap still omits/lacks the live line; already-required live gap text → no remint thrash.  
2. **HOLLOW_MINT** — hosted Yes and synth seats hollow  
3. **OPERATOR_OMIT** — durable meta omit, no heard, not hollow  
4. **NATIVE_OMIT** — native open already orients  
5. **KEEP_REQUIRED** — otherwise keep/mint  

Intentional omit must clear EDL + WAV + seats atomically. Heard artifacts always beat gap omit.

## Floor / heal

- Single `have()` / `need()` — no divergent counters for policy.
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
