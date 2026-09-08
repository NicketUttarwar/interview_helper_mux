# Homunculus 0.1.0 — gate combination classes (R1b)

Finite reachable classes under full-auto / partial-auto. Empty reachable cell = incomplete research.

| Automation | G0 | Preclean | G-Framing | VoiceRef/G1 | DeliveryUnlock | G-Publish | Reachable? | Preventable breaks / pin |
|------------|----|----------|-----------|-------------|----------------|-----------|------------|--------------------------|
| full-auto | closed (e2e_soft) | before-ingest or skip stamp | Yes auto | approved / synth | unlocked | local package | yes | gate lie if stamp without artifacts |
| full-auto | open | any | any | any | any | any | yes | analysis blocked; pin transcript_review |
| full-auto | closed | deferred (partial timing N/A) | Yes | G1 skip-optional | unlocked | advisories skip-upload | yes | ship honesty; never auto-S3 on advisories |
| full-auto | closed | skip | No sticky | N/A | unlocked | local | yes | native-only; no VO seats required |
| full-auto | closed | any | Yes | G1 open seats | unlocked | any | yes | filter defers G1_CONSUMERS; skip-then-consume if edl forced |
| full-auto | closed | any | Yes | approved | **locked** | any | yes | structural invalidate refuses; thrash if ignored |
| partial-auto | closed | deferred until after G0 | Yes | pending | unlocked | no auto S3 | yes | G0/G-Publish still operator |
| partial-auto | open | deferred | any | any | any | any | yes | must not identical-halt forever — escalate |
| manual | any | any | any | any | any | any | note-only | operator owns gates |

### Homunculus gate categories × actions

| Category | open | auto_resolve | present_operator | skip |
|----------|------|--------------|------------------|------|
| transcript_integrity (G0) | yes | **refused** | yes | **refused** |
| framing_consent | yes | yes (hosted) / skip monologue | yes | yes |
| vo_pickup (G1) | yes | automation_pending | yes | skip-optional path |
| source_preclean | never_auto | — | offer | skip stamp |
| publish_package | when master.wav | — | G-Publish | skip-upload |
| quality_ship | limit_exhausted | — | halt | — |
| others | mostly closed | soft | soft | soft |
