# Target Spec — vernacular_segment_sanitize

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| zones missing/corrupt | Honest skip stub (`skipped=…`) + heal/done (HS-5) | Completes unattended |
| no / empty zones | Same honest skip + done | Completes |
| no manifest | Honest skip + done | Completes |
| corrupt manifest + `fail_open=true` (default) | Skip stub + done | Completes (logged) |
| corrupt manifest + `fail_open=false` | `RuntimeError` — no done | Hard stop (`FULL_AUTO_REGRESSION_RISK` if default flipped) |
| zones present + sanitize OK | Rewrite manifest + resplit_report + must_keep + zones segment_ids → heal | Completes |
| sanitize exception + fail_open | Error report (`error` string, rows=[]) + heal | Completes with honest error stub |
| write fail after in-memory success + fail_open | **Today:** return without heal — incompleteness should pin | Prefer honest error stub + incomplete/heal, not silent limbo |
| boundaries.json missing | Stage still runs (body never requires it) | Completes — contract hard claim is wrong |

## Rules set (prefer deterministic)

- admit / skip when zones absent/empty or manifest absent (honest skip stub)
- admit / resplit when zones+manifest readable
- refuse / only when `fail_open=false` and corrupt/sanitize/write fail
- wait_for_gate / never
- incomplete / missing or hollow `vernacular/resplit_report.json` (HS-5) unless vernacular-restamped manifest
- precise invalidate / low_conf + fuse (claim OK if profiles match)
- auto_resolve_default / keep `audio_probes.fail_open=true`

## Complexity subtraction list

- Contract hard `segments/boundaries.json` — unused by body; demote/remove
- Soft `manifest` + `protected_zones` are the real prerequisites — promote appropriately (zones soft-ok for skip; manifest soft-ok for skip)
- Soft `run_golden_facts` unused (correctly not mutated — keep out of writes)
- Soft `speaker_flows` producer claim `transcribe` — verify ownership; advisory only
- Contract `volley_retry` / lifecycle `llm_execute` on process stage
- StageInfo vs HS-5 dual completeness story — prefer HS-5 SSOT; document empty required_outputs if intentional
- Mid-write fail_open return without report/heal — subtract limbo

## Contract / dependency deltas (proposed; not applied)

- Hard: none required for skip-complete; soft: `segments/manifest.json`, `transcript/protected_zones.json`, optional flows/tags
- Drop hard boundaries (or move soft if used by sanitize helper — verify; body doesn't read it)
- Outputs: keep resplit_report primary; manifest/must_keep/zones as co-writes
- Remediation: `full_stage_rerun` only
- Align StageInfo required_outputs with HS-5 primary (`vernacular/resplit_report.json`) if GUI still empty

## Non-goals

- Vernacular pattern / min_child_ms tuning quality
- Mutating `analysis/run_golden_facts.json`
- Local heavy ML / probe internals
- Flipping default `fail_open` to false for “stricter” Partial

## Acceptance checks

- Missing zones → skip stub with `skipped` + done; incompleteness None
- Empty zones → same
- Corrupt manifest + fail_open → skip + done
- Successful resplit → report has `rows` list; manifest `_meta.producer_stage=vernacular_segment_sanitize`
- Write-fail path: either incompleteness non-None **or** honest error report + done — never done-without-honest-report and never silent limbo without heal pin
- After VSS-B1: contract no longer claims hard boundaries

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| VSS-B1 | P0 | unambiguous | Align contract inputs to body: drop hard boundaries; soft manifest+zones | dependency data + verify | 2 | no |
| VSS-B2 | P1 | unambiguous | Drop `volley_retry` + `llm_execute` noise on process stage | dependency data | 2 | no |
| VSS-B3 | P0 | unambiguous | Write-fail (`fail_open`): persist honest error/skip report and heal **or** leave incomplete without prior false done — no bare `return` limbo | test_hs5 + write-fail fixture | 1,2 | no |
| VSS-B4 | P2 | unambiguous | Align StageInfo required_outputs with HS-5 primary report (or document empty as intentional) | web/stages.py + HS-5 tests | 2 | no |
| VSS-B5 | P2 | needs_you | Keep `audio_probes.fail_open=true` default? (recommend keep) | defaults inventory | 1,5 | **yes** if default false |

## Defaults inventory impact

- Rows touched: Stage-local landmine — `audio_probes.fail_open=true`; `sanitize.min_child_ms=800`; enforcement_mode shadow vs authoritative; HS-5 incompleteness is done gate

## target_status

`draft` — Wave 2 applied VSS-B1–B4; VSS-B5 still `needs_you`
