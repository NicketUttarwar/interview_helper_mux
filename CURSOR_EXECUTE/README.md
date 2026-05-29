# CURSOR_EXECUTE

Isolated, portable runner for **markdown-driven Cursor Agent command queues**. Uses the [Cursor SDK](https://cursor.com/docs/sdk/python) (`cursor-sdk`) with a **local** agent against your project repo.

Does **not** use the repo-root `.venv` or `interview_mux` package.

## Quick start

```bash
export CURSOR_API_KEY="cursor_..."   # https://cursor.com/dashboard/integrations

# From repository root:
./CURSOR_EXECUTE/run.sh docs/build-out/gap-closure-agent-commands.md --dry-run

# Run Phase 6 commands only (default parser: ## Command N —)
./CURSOR_EXECUTE/run.sh docs/build-out/gap-closure-agent-commands.md --from 1 --to 13

# Include historical GC-* sections in the same file
./CURSOR_EXECUTE/run.sh docs/build-out/gap-closure-agent-commands.md --include-legacy-gc
```

First run creates `CURSOR_EXECUTE/.venv` via `bootstrap_venv.sh`.

## Entry point

Only **`run.sh`** is the public interface:

```bash
./CURSOR_EXECUTE/run.sh <path-to-commands.md> [flags]
```

| Flag | Purpose |
|------|---------|
| `--dry-run` | Parse + prompt sizes; no API (no API key required) |
| `--from N` / `--to N` | Command index range |
| `--include-legacy-gc` | Also run `## GC-* —` headers |
| `--skip-done` | Skip sections marked done / `[x]` |
| `--resume` | Continue after last successful command |
| `--repo-root PATH` | Override git repo root |
| `--no-expand-attachments` | Skip inlining `@path` files |

Environment:

| Variable | Default |
|----------|---------|
| `CURSOR_API_KEY` | required for real runs |
| `CURSOR_EXECUTE_MODEL` | `composer-2.5` |
| `CURSOR_EXECUTE_MAX_PROMPT_CHARS` | `400000` |
| `CURSOR_EXECUTE_MAX_ATTACHMENT_CHARS` | `80000` |

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | All commands completed |
| `1` | SDK startup failure |
| `2` | Agent run failed (`status != finished`) |
| `3` | Parse / config / prompt size |
| `4` | Git / repo root failure |
| `5` | Bootstrap / venv failure |
| `130` | Ctrl+C |

On failure the runner **stops immediately** and prints a **loud FATAL banner** with log paths.

## Logs

Each session writes:

```text
CURSOR_EXECUTE/logs/session_<timestamp>_<pid>/
  transcript.log       # full stdout+stderr (tee)
  events.jsonl         # structured events
  last_failure.json    # on fatal exit only
```

## Markdown conventions

Runnable sections must use:

```markdown
## Command 1 — GC-Q1: Title here

```text
Agent prompt body...
Optional Read:
@docs/build-out/stage-registry.md
```
```

`@paths` are expanded into the prompt before sending to the SDK.

## Portability

Copy the entire `CURSOR_EXECUTE/` folder into another git repository. Run:

```bash
./CURSOR_EXECUTE/run.sh path/to/your/commands.md
```

Keep command markdown anywhere in that repo; runner auto-detects `git` root.

## Limitations

- Requires Cursor local SDK bridge and API billing for non-dry runs
- Does not auto-run shell “final verification” blocks from markdown
- SDK may not capture Cursor IDE logs outside `run.messages()`
