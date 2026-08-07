# Refinement Passes (canon) — slim Pass-2

> **North star:** absolute best listener outcome for *this* unknown source tape.
> Default delivery only runs **agenda + gap recompose + framing apply**. Legacy `*_refine`
> stubs remain callable for manual/legacy runs but are **not** in `DELIVERY_ORDER`.

## Default delivery path

```
gap_framing_compose (draft)
  → full_master_ranking
  → refinement_agenda (L0 confirm)
  → gap_framing_recompose OR skip-copy
  → selection_framing_apply
  → transitions → sound_design_plan → …
```

Canonical order: `src/interview_mux/v2/config.py` `DELIVERY_ORDER`.

## Architecture (still available)

1. **L0 agenda** (`understanding/refinement_agenda.json`) — confirm after ranking
2. **L1 gate** (`understanding/refinement_plan.json`) — activate|skip per pass
3. **CFI + ledger** — max one refinement per CFI per run
4. **Whitelist (slim)** — default: `gap_framing_recompose`, `selection_framing_apply` only
5. **Champion / evidence / shadow** — retained for the active gap path
6. **Flow integrity** — skip-copy draft→final so G1 always reachable

## Legacy stubs (not in DELIVERY_ORDER)

`ranking_refine` · `narrative_arc_refine` · `transitions_refine` · `sdp_intent_refine` · `edl_narrative_refine`

These are identity no-ops in `refinement_passes.py` and listed under `_LEGACY_STAGE_ALIASES` in `web/stages.py`. Re-enable only via whitelist + optional succession rules for experiments — never as the default ship path.

## No spend caps

Refinement passes are **deterministic, local rewrites** — not additional LLM calls. Anti-loop control is the CFI ledger cap only.

## Priors / shadow / mid-pass

Unchanged for the active gap path — see module list below. Shadow scores remain informational when a pass is skipped.

## Modules

| Module | Role |
|--------|------|
| `refinement_identity.py` | CFI registry |
| `refinement_ledger.py` | Ordered call ledger |
| `refinement_catalog.py` | Pass catalog + slim whitelist |
| `refinement_policy.py` | Tape character + policy packs |
| `refinement_priors.py` | Soft L0 priors |
| `refinement_succession.py` | Unlock/mutex helpers (legacy rules opt-in) |
| `refinement_agenda.py` | L0 agenda |
| `refinement_gate.py` | L1 activate\|skip |
| `refinement_evidence.py` | Evidence packets |
| `refinement_kernels.py` | Deterministic scoring |
| `refinement_champion.py` | Champion store |
| `refinement_accept.py` | Accept/reject |
| `refinement_shadow.py` | Informational shadow scores |
| `refinement_passes.py` | Stage runners |
| `refinement_flow_integrity.py` | Skip-copy draft→final |

## Schemas

`refinement_agenda.schema.json`, `refinement_ledger.schema.json`, `refinement_plan.schema.json` — see [json-schema-coverage.md](./json-schema-coverage.md).
