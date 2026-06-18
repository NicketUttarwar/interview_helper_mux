# Blocker tickets

When the GUI driver stalls, hits an LLM `gate`, or cannot resolve a checkpoint, it writes:

```text
blockers/BLOCKER-NNN-<slug>.md
```

## Naming

- `NNN` — zero-padded sequence (001, 002, …)
- `<slug>` — short kebab-case symptom (`stuck-write-approval`, `llm-gate-content-context`)

## Status lifecycle

| Status | Meaning |
|--------|---------|
| `open` | Driver stopped; needs fix |
| `fixed` | E2E-03 agent applied fix; safe to `--resume` |
| `waived` | Accepted skip with documented rationale |

## Fix comment (required)

The **E2E-03** agent must fill:

- **Root cause** — what broke
- **Fix** — files changed
- **Fix comment** — plain-language note for the operator

## Resume

```bash
./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --resume
```
