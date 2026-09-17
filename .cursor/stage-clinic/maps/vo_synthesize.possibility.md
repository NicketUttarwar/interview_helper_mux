# Possibility Map — vo_synthesize

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- delivery #55 | process | primary `mastering/vo_synthesize.json` + WAV trees
- G1 gate | Chatterbox/local TTS model quality: N/A (clinic host honesty only)
- OpenAI: N/A on this stage

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| transitions present | synthesize_spoken_transitions (fail-open log) | IN_CODE | |
| gap present | resync_required_synthesize_wavs + bind heal | IN_CODE | |
| still missing pairs | persist report; incompleteness | IN_CODE | `vo_synthesize_pair_incompleteness` |
| G1 missing | incompleteness / gate open | IN_CODE | `check_g1_vo` |
| seated missing WAV | incompleteness — **done-without-wav forbidden** | IN_CODE | `seated_vo_missing_ids` |
| contract hard only gap | understates transitions need | CODE_DOC_CONFLICT | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gap/air unsanitary | incompleteness pin sanitize | IN_CODE | |
| deferred pairs | thrash hardening may allow/deny done | IN_CODE | `vo_done_with_deferred_pairs_ok` |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| G1 open record | needs_operator / hard_block | IN_CODE | `resolve_g1_vo_gate` |
| G1 Chatterbox Full-auto | automation_pending synthesize_all | IN_CODE | chatterbox_owned |
| G1 optional | may skip optional | IN_CODE | `v2_g1_optional` |
| illegal skip with missing WAV | incompleteness / HV4 | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean | report + assert_seated_vo_rendered + hard seat freeze | IN_CODE | |
| synth fail-open then missing | not done | IN_CODE | |
| hard freeze stamp fail | raise | IN_CODE | |
| done-without-wav | reconcile clears done | IN_CODE | honesty DoD |

## 5. Side effects

- Writes vo_synthesize.json, master/transitions/*.wav, vo_pickup/** — IN_CODE
- Hard seat freeze — IN_CODE
- Invalidates edl_narrative_audit, edl — contract

## 6. Complexity traps

- Local TTS quality: N/A (one-line)
- Host honesty: WAV presence / G1 / seated bind — IN_CODE
- Dual SSOT transitions vs gap VO — IN_CODE

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard gap only | also needs transitions for pairs | CODE_DOC_CONFLICT |
| soft [] | many implicit deps | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A OpenAI | | IN_CODE | |
| Chatterbox fail | missing WAV → incomplete (not soft-done) | IN_CODE | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + Chatterbox + voice_ref | driver synthesizes; no human | IN_CODE | operator_gate_view |
| Full-auto record-required line | human stall OR needs_operator | FULL_AUTO_REGRESSION_RISK | |
| optional G1 skip | pair freeze earlier; may hollow | FULL_AUTO_REGRESSION_RISK | HV4 |
| GUI-only dependency? | record UI if not chatterbox_owned | IN_CODE | |
| partial-only fix risk | never mark done without WAVs for partial | IN_CODE | |

## Flags (§5.5)

- G1 optional (`v2_g1_optional`)
- gap_vo delivery chatterbox vs record
- mix.missing_vo_retry_once (later net)

## TEST_GAP

- contract hard inputs expand to transitions
- assert_seated_vo_rendered vs defer_done interaction

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [x] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [x] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Expand contract hard inputs to transitions.json?

## discovery_status

`complete`
