# Possibility Map — {{STAGE_ID}}

brain: 0.2.0 | discovery_status: not_started  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index (copy from dossier when filled)

- tier / primary path / gate adjacency / LLM class:

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | | | |
| hard missing | | | |
| soft missing | | | |
| soft stale | | | |
| hollow `{}` / `[]` | | | |
| schema-valid semantic junk | | | |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | | | |
| producer invalidated | | | |
| epoch / delivery drift | | | |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| gate open / waiting | | | |
| gate answered | | | |
| illegal skip | | | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | | | |
| soft fail | | | |
| hard fail | | | |
| partial persist | | | |
| done-without-primary | | | |
| retry / heal loop | | | |
| identical halt | | | |

## 5. Side effects

- Writes (actual):
- Forbidden writes risk:
- Invalidates:
- Consumers:

## 6. Complexity traps

- OpenAI/external control vs rules:
- Multi-heal / caps:
- Dual SSOT:
- Local heavy ML: _(one-line N/A if any)_ 

## 7. Contract honesty (declared-vs-actual)

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard inputs | | |
| soft inputs | | |
| outputs | | |
| invalidates / consumers | | |
| remediation | | |

## 8. External service variance (OpenAI / cloud)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| malformed JSON | | | |
| schema fail | | | |
| retry exhausted (≤2) | | | |
| hollow persist | | | |
| N/A (no external LLM) | | | |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults happy path | | | |
| human stall required? | | | |
| GUI-only action dependency? | | | |
| auto-accept / default must fire | | | |
| partial-only fix risk | | | |

## DoD threats (tag which §0.2 checks this stage threatens)

- [ ] 1 Progression  [ ] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [ ] 5 Defaults  [ ] 6 Ship bar  [ ] 7 Cross-stage

## Open questions for operator

1.

## discovery_status

`not_started` | `in_progress` | `needs_you` | `complete` | `waived`
