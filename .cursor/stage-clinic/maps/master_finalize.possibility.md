# Possibility Map — master_finalize

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process | primary: master.wav + PMQ | seed #66
- module: `mastering.run_master_finalize` → `run_post_master_quality` → `run_authoritative_listen_delight_at_ship`
- listen_delight_audit (seed #60): advisory pre-mix (`fail_early_at_audit_stage` claim); **authoritative ship gate is here**
- gates: g_listen_mode=block default; optimizer take-best; aspirational_quality
- thrash: optimizer↔junction | tests: solid

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| assembly/edl missing | StageInputIssue (+ edl archive restore try) | IN_CODE | `_check_master_finalize` |
| selection≠edl order | refuse | IN_CODE | order_hashes_match |
| assembly_ledger incomplete | refuse unless e2e_soft_junction | IN_CODE | |
| seam commitment≠committed | refuse (commitment_blocks_finalize) | IN_CODE | |
| bridge_completeness incomplete | refuse | IN_CODE | |
| hollow/truncated master | committed_master_integrity_ok blocks soft-complete | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| optimizer take-best remaster | Re-run `run_junction_snip_qa` then loudnorm | IN_CODE | |
| PMQ | Rebuilds post_master autopsy / delight rewrite | IN_CODE | ownership dual ALLOW |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| g_listen pending + mode=block | `_gate_exit` — human | IN_CODE | `require_g_listen_clear` |
| g_listen mode warn | Log only | IN_CODE | |
| timeline optimizer uncleared | require_timeline_optimizer_clear | IN_CODE | |
| G-Publish | mark pending after success — does not block finalize | IN_CODE | mark_g_publish_pending |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | master.wav + PMQ pass + delight pass → g_publish pending | IN_CODE | |
| optimizer apply fail | Loud hard stop (no e2e bypass) | IN_CODE | |
| aspirational enabled | May produce master with advisories; floors catastrophic still hard | IN_CODE | aspirational_quality |
| PMQ structural fail | block=True path | IN_CODE | |
| delight fail non-aspirational | Hard ship stop | IN_CODE | |
| heal | omit_ledger air-contract; VO script sync; layup gap authority | IN_CODE | |

### listen_delight relationship (IN_CODE)

```
listen_delight_audit (pre-mix, advisory)
  → mix may refresh advisory
  → master_finalize → master.wav
  → run_post_master_quality → run_authoritative_listen_delight_at_ship
       (pass_phase=post_master; NORTH_STAR ship gate)
```

## 5. Side effects

- master.wav, post_master_quality.json, listener_scorecard.json, listen_delight_audit rewrite, post_master seam_autopsy, g_publish_pending — `IN_CODE`

## 6. Complexity traps

- StageInfo understates delight/PMQ (loudness-only copy) — `CODE_DOC_CONFLICT`
- Pre-mix delight mistaken for ship — `IN_CODE` threat
- Dual autopsy ownership — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| outputs delight+autopsy | Matches ship rewrite | IN_CODE |
| soft delight from audit stage | Authoritative rewrite at ship | IN_CODE |
| llm_execute lifecycle | Misleading | CODE_DOC_CONFLICT |
| hard junction QA | + commitment/ledger/render extras in `_check` | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| delight/PMQ LLM dims | Variance on ship floors (overall_min 0.9) | IN_CODE | |
| ≤2 / refuse | Via delight stack — verify no soft-done | UNKNOWN | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Happy | commitment + g_listen clear + PMQ/delight → master + g_publish pending | IN_CODE | |
| g_listen_mode=block + pending | **Stalls** — product seed walk does not auto-clear | IN_CODE | FULL_AUTO_REGRESSION_RISK |
| tools/full_auto_driver | clear_g_listen | IN_CODE | driver-only |
| aspirational + advisories | Master may exist; S3 later blocked by require_operator_publish_when_advisory | IN_CODE | |
| e2e_soft | Gate-only — not quality floors | IN_CODE | |
| human stall? | g_listen; optional optimizer | IN_CODE | |
| GUI-only? | G-Listen | IN_CODE | |
| partial-only fix risk | Auto-clear g_listen in Partial would weaken listen gate | | yes |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| sound_design.g_listen_mode | block | Finalize stall |
| post_master_quality.overall_min | 0.9 | Ship floor |
| listen_delight.mode | authoritative | Ship rewrite |
| aspirational_quality.enabled | true | Advisory ship path |
| require_operator_publish_when_advisory | true | S3 later |
| commitment_blocks_finalize | true | Hard seal |
| timeout | 600 | |

## TEST_GAP

- Product Full-auto without driver: g_listen matrix
- aspirational on vs off ship floors

## DoD threats

- [x] 1–7 (hollow master, delight mistaken, g_listen stall, optimizer cascade, aspirational leak, dual autopsy, publish floors)

## Open questions

1. Unattended Full-auto: skip g_listen or auto-clear?
2. Is aspirational advisory master “ship success” under NORTH_STAR?

## discovery_status

`complete`
