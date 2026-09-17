# Target Spec — audio_preclean

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| auto_run accept | isolated.wav + lineage + done | DeepFilter/ffmpeg runs unattended |
| operator/dismiss skip | skip.json present + stage done + prepare_outputs true | no stall; ingest uses raw input |
| heal incompleteness | skip.json satisfies completion OR explicit n_a primary | dual SSOT removed |

## Rules set (prefer deterministic)

- admit / when scope enabled and source exists
- refuse / missing source when enabled
- wait_for_gate / never for defaults auto_run
- incomplete / never leave skip.json without done
- precise invalidate / only on accept path (existing)
- auto_resolve_default / auto_run_before_ingest stamps accept decision

## Complexity subtraction list

- Dual completion story: STAGE_ARTIFACT_DISK_PATHS isolated-only vs agenda skip.json

## Contract / dependency deltas (proposed; not applied)

- Soft input should be run input / optional normalized_rebuild, not always ingest/normalized
- Document auto_run default vs operator-gates "never auto-run" claim

## Non-goals

- DeepFilter model tuning

## Acceptance checks

- ensure_preclean_skipped → is_done True and stage_artifact_incompleteness None
- HP-3 tests pass without mark_done_raw

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| B1 | P0 | unambiguous | Make stage_artifact_incompleteness treat preclean/skip.json as complete (align heal with prepare_outputs / HP-3) | pytest test_hp3 + ensure_preclean_skipped marks done | 1,2 | no |
| B2 | P1 | unambiguous | Fix contract soft input + remediation claims to host rerun | contract YAML via dependency data | 2 | no |
| B3 | P1 | needs_you | Resolve docs "Never auto-run" vs defaults auto_run_before_ingest=true | inventory row + gates doc | 5 | yes if flipping default |

## Defaults inventory impact

- Rows touched: Offers that must not block / Stage-local landmines — preclean auto_run

## target_status

`draft`
