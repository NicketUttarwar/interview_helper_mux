# Target Spec — master_finalize

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| integrity+commitment+delight floors | master.wav + PMQ | Completes; arms G-Publish |
| g_listen pending Full-auto | auto_resolve_default | No permanent stall |
| optimizer take-best | Remaster + junction re-seal then master | Deterministic |
| aspirational advisory | Master OK; remote publish gated honestly | Local progress |

## Rules set

- never mark_done without master.wav + PMQ artifact
- refuse without commitment seal
- wait_for_gate g_listen only Partial; Full-auto auto_resolve (needs_you)
- precise invalidate on optimizer remaster
- authoritative delight at ship — never treat pre-mix audit as ship

## Complexity subtraction

- StageInfo copy fix
- One ship-gate SSOT (PMQ+authoritative delight)

## Acceptance checks

- require_g_listen_clear behavior under Full-auto inventory
- committed_master_integrity_ok
- mark_g_publish_pending after success
- optimizer fail is loud

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | StageInfo copy includes PMQ/delight | stages.py | 2 | no |
| B2 | P0 | needs_you | Full-auto g_listen auto-clear policy | defaults inventory | 3,5 | yes |
| B3 | P0 | needs_you | aspirational advisory vs NORTH_STAR ship | ship bar | 6 | yes |
| B4 | P1 | unambiguous | Drop llm_execute lifecycle | YAML | 7 | no |

## Defaults inventory impact

- g_listen_mode=block; aspirational + require_operator_publish_when_advisory; PMQ floors

## target_status

`draft`
