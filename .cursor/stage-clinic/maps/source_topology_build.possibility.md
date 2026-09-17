# Possibility Map — source_topology_build

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process / deterministic classify — `IN_CODE` (contract process)
- primary: `understanding/source_topology.json` (+ flow_adaptation) — `IN_CODE`
- gate adjacency: pickup confirm may auto under auto_accept_defaults — `IN_CODE`
- LLM: none

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | reads understanding/speakers.json + transcript | IN_CODE | `build_topology_artifacts` |
| hard missing | read_json fails | IN_CODE | |
| soft missing | soft transcript/normalized not separately gated | IN_CODE | |
| hollow speakers | classify still runs; weak topology | IN_CODE | |
| semantic junk | wrong roles → wrong pickup | IN_CODE | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | after speaker_roles | IN_CODE | |
| preserves pickup overrides | if prior adaptation confirmed | IN_CODE | `run_source_topology_build` |
| incompleteness | requires topology **and** flow_adaptation | IN_CODE | `_source_topology_incompleteness` |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| pickup pending | `check_pickup_speaker_pending`; Full-auto may `maybe_auto_confirm_pickup_speaker` when auto_accept_defaults / env | IN_CODE | `gap_vo_gates.auto_accept_gap_gate_defaults_enabled` |
| illegal skip | mark_done without confirm leaves pending for later gap gates | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | write topology+adaptation → mark_done → maybe auto confirm | IN_CODE | |
| soft fail | none | IN_CODE | |
| hard fail | missing speakers | IN_CODE | |
| done-without-primary | HU-4 incompleteness both files | IN_CODE | |
| sample wavs | optional; not required for done | IN_CODE | comment HU-4 |
| identical halt | UNKNOWN | UNKNOWN | |

## 5. Side effects

- Writes: source_topology.json, flow_adaptation.json, optional speaker_samples — `IN_CODE`
- Contract invalidates many downstream — live clear_from on rewrite? typically via producer invalidation rails — verify `UNKNOWN` for automatic invalidate list
- Consumers: content_context hard, framing, ranking, etc. — contract

## 6. Complexity traps

- OpenAI: none
- Dual SSOT: topology vs flow_adaptation pickup fields
- Local ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard speakers.json | enforced via read | IN_CODE |
| soft transcript+normalized | transcript used in stats | IN_CODE |
| outputs topology+adaptation+samples | samples optional | IN_CODE |
| invalidates long list | claim; code may not clear all on write | UNKNOWN |
| remediation volley_retry | host | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | N/A | IN_CODE | |

## 9. Full-auto / defaults path

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto happy path | classify + mark_done; pickup auto-confirm if INTERVIEW_MUX_AUTO_ACCEPT_GATES / gap auto_accept_defaults | IN_CODE | |
| human stall? | Partial may leave pickup unconfirmed until G-Framing | IN_CODE | |
| GUI-only? | adaptation patch GUI optional | IN_CODE | |
| auto-accept must fire | for unattended gap path later | IN_CODE | defaults inventory landmine candidate |
| partial-only fix risk | forcing confirm in partial would regress MUST_ACT framing later | FULL_AUTO_REGRESSION_RISK | |

## DoD threats

- [ ] 1 Progression  [ ] 2 Honesty  [x] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [ ] 7 Cross-stage

## Open questions for operator

1. _(none for L1)_

## discovery_status

`complete`
