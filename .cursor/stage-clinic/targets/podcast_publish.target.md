# Target Spec — podcast_publish

brain: 0.2.0 | target_status: applied

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| package inputs present | package_ready.ready=true | Completes local |
| Skip | package_ready ready:false skipped OR incompleteness exemption | Honest seed |
| Full-auto + advisories | Local done; remote refused honestly (no silent hang; no auto-consent) | DONE-local / refuse-remote |
| Partial G-Publish open | wait_for_gate | Must-act |

## Rules set

- admit local package when wav+mp3+cover+VTT present
- incomplete hollow package_ready
- skip writes ready:false skipped
- wait_for_gate Partial only
- **B2:** never auto-consent advisories; stamp `g_publish_remote_refused`; Full-auto clears pending hang
- **B4 KEEP DEAD:** never wire `require_g_publish_clear` without Full-auto bypass

## Complexity subtraction

- Delete or document dead require_g_publish_clear — KEEP DEAD documented
- Single SSOT: stage=local; sync=post with explicit consent rules

## Acceptance checks

- HPUB-2 skip honesty
- remote_publish_allowed no e2e soft waiver
- Partial must-act unchanged
- boto3-only
- Full-auto advisory sync → refuse + no pending hang

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Skip: package_ready ready:false skipped OR HPUB-2 exemption | incompleteness | 2 | no |
| B2 | P0 | answered | DONE-local / refuse-remote (no auto-consent) | note_remote_publish_refused | 1,5,6 | applied |
| B3 | P1 | unambiguous | Contract hard: mp3+cover+VTT | dependency data | 7 | no |
| B4 | P1 | answered | KEEP DEAD require_g_publish_clear | AST pin | 3,5 | n/a kept |
| B5 | P2 | unambiguous | Stop over-soft contract inputs | YAML | 7 | no |
| B6 | P2 | unambiguous | Tests: skip honesty + advisory sync Full-auto | pytest | 1,2 | no |

## Defaults inventory impact

- G-Publish Partial must-act; aspirational advisory S3 block; dead require_g_publish_clear kept
- Full-auto: local package + refuse-remote stamp (no hang)

## target_status

`applied`
