# Possibility Map — podcast_publish

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process | primary: package_ready.json ready:true | seed #72
- module: `run_podcast_publish` / `run_podcast_publish_skip`
- gate: G-Publish UI/journey; stage body **ungated** (`require_g_publish_clear` defined never called)
- AWS: boto3 only (`podcast_rss/s3_publish.py`) — never AWS CLI
- thrash: no | tests: solid local honesty

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| master.wav missing | FileNotFoundError | IN_CODE | |
| mp3/cover/VTT empty | FileNotFoundError after materialize | IN_CODE | |
| VTT missing | inline `run_master_transcript_build` | IN_CODE | |
| cover missing | png convert or `_copy_show_fallback` | IN_CODE | |
| cover <1400px | require_cover_min_size hard | IN_CODE | |
| meta missing | Untitled fallback | IN_CODE | |
| PMQ not publishable | require_publishable loud | IN_CODE | advisories do **not** block local package |
| skip path | publish_result skipped + mark_done **without** package_ready.ready | IN_CODE | HPUB-2 hollow risk |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| invalidated by master_transcript ADG | Asymmetric | IN_CODE | |
| soft contract edl/selection/gap unused | Over-declare | CODE_DOC_CONFLICT | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Partial MUST_ACT g_publish | wait_for_operator_g_publish | IN_CODE | partialOperatorGates / automation_run |
| Prepare | clear_g_publish + run ship stages | IN_CODE | server.g_publish_continue |
| Skip | clear skipped + run_podcast_publish_skip | IN_CODE | |
| require_g_publish_clear | **Dead rail — never called** | IN_CODE | gates.py only def |
| Full-auto | Does not wait Prepare; packages + may sync | IN_CODE | |
| Wiring require into stage body | Would stall Full-auto | FULL_AUTO_REGRESSION_RISK | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | package_ready ready:true; publish_result uploaded:false; mark_done | IN_CODE | |
| skip | skipped result + mark_done; no ready | IN_CODE | honesty threat |
| hollow chapters-only | incompleteness package_ready | IN_CODE | HPUB-2 |
| S3 sync fail | SyncResult errors; stage already done | IN_CODE | sync_assets |
| advisories block S3 | publish_blocked_quality_advisories | IN_CODE | |
| PMQ false remote | remote_publish_allowed refuse | IN_CODE | no e2e_soft waiver remote |
| boto3 missing | RuntimeError | IN_CODE | |

## 5. Side effects

- package_ready, publish_result, chapters, episode.json, description.txt, transcript.vtt, may rewrite cover_meta, copies audio/master/cover — `IN_CODE`
- StageInfo flush list documents prior hollow flush bug — `IN_CODE`
- Clears gate on skip only — `IN_CODE`
- S3 sync is **not** stage body — finish_complete_run / sync_publish_to_s3 — `IN_CODE`

## 6. Complexity traps

- Dual SSOT: local package vs G-Publish/S3 — `IN_CODE`
- Dead require_g_publish_clear — `IN_CODE`
- Skip vs ready:true — `IN_CODE`
- Inline transcript rebuild — `IN_CODE`
- Advisory consent GUI-only vs Full-auto sync — `IN_CODE`
- Local ML: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| hard: wav only | + mp3/cover/VTT/chapters effectively hard | CODE_DOC_CONFLICT |
| soft: many unused | Over-declare | CODE_DOC_CONFLICT |
| outputs | Match StageInfo flush | IN_CODE |
| invalidates [] | ADG from transcript hits this | IN_CODE |
| remediation volley_retry | Deterministic | CODE_DOC_CONFLICT |
| Docs: G-Publish after transcript | Also armed at master_finalize mark_g_publish_pending | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| OpenAI N/A | | IN_CODE | |
| AWS boto3 put/invalidate | Additive; execution_id scoped | IN_CODE | |
| advisories + no consent | S3 blocked | IN_CODE | FULL_AUTO_REGRESSION_RISK |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Happy PMQ true, no advisories | package + S3 sync | IN_CODE | |
| aspirational advisories (default on) | local OK; **S3 blocked** — driver/GUI never sets g_publish_advisory_consent in product seed | IN_CODE | FULL_AUTO_REGRESSION_RISK |
| e2e_soft + publish_allowed false | local walk OK; remote refused | IN_CODE | HPUB-1 |
| Human stall Full-auto package? | No | IN_CODE | |
| Human stall Partial S3/skip? | Yes MUST_ACT | IN_CODE | |
| GUI-only? | advisory consent / Prepare | IN_CODE | |
| auto-accept must fire? | Full-auto should consent or clear before sync — **missing on product path** | IN_CODE | |
| partial-only fix risk | Enabling require_g_publish_clear without Full-auto bypass stalls unattended | FULL_AUTO_REGRESSION_RISK | |

## Flags (§5.5)

| flag | default | effect |
|------|---------|--------|
| podcast.enabled | true | Gate pending |
| aspirational require_operator_publish_when_advisory | true | S3 block |
| post_master_quality.block_publish | false | Local packaging |
| podcast.s3.episode_files.* | | Layout |
| upload_master_wav | | Optional |

## TEST_GAP

- skip → seed-complete without ready:true
- Full-auto sync under advisories without consent
- dead require_g_publish_clear callers
- description.txt ownership via raw write_text

## DoD threats

- [x] 1 Progression (S3 advisory trap)
- [x] 2 Honesty (skip hollow)
- [x] 3 Stalls (partial)
- [ ] 4
- [x] 5 Defaults
- [x] 6 Ship bar
- [x] 7 Cross-stage (inline transcript)

## Open questions

1. Full-auto: auto-consent advisories for S3, or DONE-local refuse-remote?
2. Skip seed-complete without ready:true — special-case HPUB-2?
3. Revive require_g_publish_clear for manual only?

## discovery_status

`complete`
