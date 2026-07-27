# Setup — interview_helper_mux (v2)

Two commands:

```bash
./scripts/bootstrap_venv.sh   # once per machine (or after deleting .venv)
./scripts/run.sh            # every launch → http://127.0.0.1:8765
```

Before first run, copy secrets and add source audio:

```bash
cp config/templates/secrets.env.example config/secrets/secrets.env   # add OPENAI_API_KEY, AWS creds
mkdir -p ASSETS/input
# copy your interview.wav → ASSETS/input/
```

**North star:** [NORTH_STAR.md](NORTH_STAR.md)

Optional bootstrap flags: `BOOTSTRAP_SKIP_GUI=1`, `BOOTSTRAP_SKIP_VERIFY=1`

Optional run flags: `MUX_PRESERVE_SESSION=1`, `MUX_REBUILD_GUI=1`, `MUX_REFRESH_DEPS=1`, `MUX_SKIP_ASSETS_CLEANUP=1`

Operator journey: [docs/workflows/operator-journey.md](docs/workflows/operator-journey.md)
