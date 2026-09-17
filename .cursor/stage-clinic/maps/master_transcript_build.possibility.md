# Possibility Map — master_transcript_build

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process | primary: master/transcript.json | seed #67 | gate: G-Publish adjacency
- module: `asset_transcripts.run_master_transcript_build`
- Local STT: **N/A internals** — host remaps sidecar cues only

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| master.wav / edl missing | FileNotFoundError | IN_CODE | |
| empty spoken cues | RuntimeError via master_transcript_ship_incompleteness before mark_done | IN_CODE | HPUB-3 |
| schema cue_count:0 allowed | Ship incompleteness refuses | CODE_DOC_CONFLICT | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| re-run | ADG invalidates episode_meta_build + podcast_publish | IN_CODE | odd meta coupling |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| G-Publish | Arms after master; stage runs in ship walk | IN_CODE | |
| Prepare GUI | May re-run from this stage | IN_CODE | g_publish_continue |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | json+vtt+txt + mark_done | IN_CODE | |
| hollow | raise; no done | IN_CODE | |
| publish inline rebuild | run_podcast_publish may call this | IN_CODE | dual producer risk |

## 5. Side effects

- transcript.{json,vtt,txt}; may rewrite transcripts/index.json — `IN_CODE`

## 6. Complexity traps

- Inline rebuild from publish — `IN_CODE`
- Local STT: N/A

## 7. Contract honesty

| Declared | Actual | Tag |
|----------|--------|-----|
| sufficiency min_count 0 | HPUB-3 refuses empty | CODE_DOC_CONFLICT |
| soft index | Produced not required | IN_CODE |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Happy after master | Completes unattended | IN_CODE | |
| empty cues | Hard fail | IN_CODE | |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |

## Flags (§5.5)

- podcast.enabled for G-Publish pending adjacency

## TEST_GAP

- stale EDL vs wav; sparse VO sidecars still “complete”

## DoD threats

- [ ] 1  [x] 2  [ ] 3  [ ] 4  [ ] 5  [ ] 6  [x] 7

## Open questions

1. Empty schema-valid transcript advisory vs hard refuse?

## discovery_status

`complete`
