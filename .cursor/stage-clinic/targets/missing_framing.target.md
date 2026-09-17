# Target Spec — missing_framing

brain: 0.2.0 | target_status: draft

## Ideal behavior

| Permutation | Required outcome | Full-auto + defaults |
|-------------|------------------|----------------------|
| G-Framing pending + 0.2.0 | auto_resolve Yes (hosted) or skip monologue | No human |
| G-Framing No | skip stub; done | Continues native_only |
| Yes + eligible | Sharded OA-07; heal when scored | Completes |
| batch_fill leftovers | incomplete (HG-3) | May re-enter until seal |
| coverage CAP | seal; heal | Completes |
| ineligible + no auto_skip | loud fail | Needs classified remediation — not silent |

## Rules set

- wait_for_gate / framing pending unless auto
- auto_resolve_default / homunculus Yes
- incomplete / batch_fill + voice_ref
- refuse / ineligible hard-stop (or skip if flagged)

## Complexity subtraction

- Prefer seal over endless batch_fill thrash (already CAP=2)

## Non-goals

- Chatterbox clone quality

## Acceptance checks

- HG-3 refuse; gate auto under 0.2.0; CAP seal

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----|---------------------------|
| B1 | P0 | needs_you | Confirm Full-auto Start always arms homunculus_auto for G-Framing | inventory + StartTab | 3,5 | yes if broken |
| B2 | P0 | unambiguous | Keep batch_fill incomplete | HG-3 | 2 | no |
| B3 | P1 | needs_you | auto_skip_when_ineligible default? | intent | 3 | yes |
| B4 | P1 | unambiguous | Document AUTO_ACCEPT env vs gap_fill.auto_accept_defaults=false | inventory | 5 | no |

## Defaults inventory impact

- gap_fill.auto_accept_defaults=false; rely on brain 0.2.0 homunculus_auto
- default_framing_enabled=true

## target_status

`draft`
