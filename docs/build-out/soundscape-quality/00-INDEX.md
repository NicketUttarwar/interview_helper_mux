# Soundscape quality — execution index

**Start here.** Run **01 → 07** — one Cursor Agent chat per step (or implement sequentially in one chat when shipping the full wave).

North star: [soundscape-policy.md](../../cross-cutting/soundscape-policy.md).

## Sequence

| Step | File | Ticket | Gate |
|------|------|--------|------|
| **00** | [00-INDEX.md](./00-INDEX.md) | — | — |
| **01** | [01-WAVE-0-specs.md](./01-WAVE-0-specs.md) | docs | Schema + tickets linked |
| **02** | [02-BUILD-SS-01-policy.md](./02-BUILD-SS-01-policy.md) | BUILD-SS-01 | Policy artifact + resolve API |
| **03** | [03-BUILD-SS-02-slots.md](./03-BUILD-SS-02-slots.md) | BUILD-SS-02 | Cue slots + plan lint |
| **04** | [04-BUILD-SS-03-fitness.md](./04-BUILD-SS-03-fitness.md) | BUILD-SS-03 | Regen/skip loop executes |
| **05** | [05-BUILD-SS-04-verify.md](./05-BUILD-SS-04-verify.md) | BUILD-SS-04 | soundscape_report + remux |
| **06** | [06-BUILD-SS-05-gui.md](./06-BUILD-SS-05-gui.md) | BUILD-SS-05 | Operator overrides + panel |
| **07** | [07-FINISH-signoff.md](./07-FINISH-signoff.md) | BUILD-SS-06 | Audits + DoD |

## Standard companions

- `.cursor/rules/interview-helper-mux.mdc`
- `AGENTS.md`
- `docs/cross-cutting/soundscape-policy.md`
- `docs/cross-cutting/sound-design.md`
- `docs/build-out/ticket-specs.md` (BUILD-SS-*)
- `docs/build-out/doc-maintenance.md`
