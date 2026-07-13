# 01 — WAVE 0 specs

**Ticket:** docs (Wave 0)

## Agent directive

Ensure `docs/cross-cutting/soundscape-policy.md`, schema, stage contract, ticket-specs BUILD-SS-01…06, and remaining-build-commands soundscape section exist and match the master plan. No production code required beyond docs already landed.

## Verify

```bash
test -f docs/cross-cutting/soundscape-policy.md
test -f docs/cross-cutting/json-schemas/soundscape_policy.schema.json
test -f docs/cross-cutting/stage-contracts/soundscape_policy_build.yaml
rg "BUILD-SS-0" docs/build-out/ticket-specs.md
```
