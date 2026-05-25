# Config

Resolution order (highest wins):

1. CLI flags (`--input`, `--run-id`)
2. `config/secrets/secrets.env`
3. `config/app.defaults.json`

## Files

| File | Committed | Purpose |
|------|-----------|---------|
| `app.defaults.json` | yes | Paths, model routing |
| `templates/app.defaults.json` | yes | Copy template |
| `templates/secrets.env.example` | yes | Secrets template |
| `secrets/secrets.env` | **gitignored** | API keys |

Secrets are loaded by Python into an isolated dict — not exported to `os.environ` globally.
