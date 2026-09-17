# Target Spec — podcast_publish

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| package inputs present | package_ready.ready=true | Completes local |
| Skip | package_ready ready:false skipped OR incompleteness exemption | Honest seed |
| Full-auto + advisories | Local done; remote: auto-consent OR explicit refuse (not silent hang) | Policy needs_you |
| Partial G-Publish open | wait_for_gate | Must-act |

## Rules set

- admit local package when wav+mp3+cover+VTT present
- incomplete hollow package_ready
- skip writes ready:false skipped
- wait_for_gate Partial only
- auto_resolve_default Full-auto advisory consent (needs_you)
- never wire require_g_publish_clear without Full-auto bypass

## Complexity subtraction

- Delete or document dead require_g_publish_clear
- Single SSOT: stage=local; sync=post with explicit consent rules

## Acceptance checks

- HPUB-2 skip honesty
- remote_publish_allowed no e2e soft waiver
- Partial must-act unchanged
- boto3-only

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | unambiguous | Skip: package_ready ready:false skipped OR HPUB-2 exemption | incompleteness | 2 | no |
| B2 | P0 | needs_you | Full-auto advisory consent before S3 sync | defaults inventory | 1,5,6 | yes |
| B3 | P1 | unambiguous | Contract hard: mp3+cover+VTT | dependency data | 7 | no |
| B4 | P1 | needs_you | Delete or wire require_g_publish_clear with Full-auto bypass | gates | 3,5 | yes |
| B5 | P2 | unambiguous | Stop over-soft contract inputs | YAML | 7 | no |
| B6 | P2 | unambiguous | Tests: skip honesty + advisory sync Full-auto | pytest | 1,2 | no |

## Defaults inventory impact

- G-Publish Partial must-act; aspirational advisory S3 block; dead require_g_publish_clear; Full-auto missing consent

## target_status

`draft`
