# Target Spec — master_finalize

brain: 0.2.0 | target_status: applied

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| integrity+commitment+delight floors | master.wav + PMQ | Completes; arms G-Publish |
| g_listen pending Full-auto | auto_resolve_default | No permanent stall |
| optimizer take-best | Remaster + junction re-seal then master | Deterministic |
| aspirational advisory | **Local master = ship OK** (campaign NORTH_STAR bar); remote publish still gated | Local progress |

## Rules set

- never mark_done without master.wav + PMQ artifact
- refuse without commitment seal
- wait_for_gate g_listen only Partial; Full-auto auto_resolve via shared helper
- precise invalidate on optimizer remaster
- authoritative delight at ship — never treat pre-mix audit as ship
- **B3:** aspirational advisory local master counts as ship success for campaign bar (remote still advisory-blocked)

## Complexity subtraction

- StageInfo copy fix
- One ship-gate SSOT (PMQ+authoritative delight)

## Acceptance checks

- require_g_listen_clear behavior under Full-auto inventory
- committed_master_integrity_ok
- mark_g_publish_pending after success
- optimizer fail is loud
- aspirational + catastrophic-ok → advisory soft-proceed at ship (F7 1C pin)

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | StageInfo copy includes PMQ/delight | stages.py | 2 | no |
| B2 | P0 | done | Full-auto g_listen auto-clear policy | `maybe_auto_clear_g_listen_for_full_auto` + pytest | 3,5 | no (Full-auto fixed; Partial keeps block) |
| B3 | P0 | answered | Advisory = ship OK for campaign bar | notes + F7 1C pin | 6 | applied (binding) |
| B4 | P1 | unambiguous | Drop llm_execute lifecycle | YAML | 7 | no |

## Defaults inventory impact

- g_listen_mode=block; aspirational + require_operator_publish_when_advisory; PMQ floors
- B3: local aspirational advisory master = campaign ship success; S3 still gated

## target_status

`applied` — B1/B2/B3/B4 closed
