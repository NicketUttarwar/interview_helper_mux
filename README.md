# interview_helper_mux

Turn a long-form interview recording into a **mastered podcast** (`master/master.wav`).

**Setup once, then launch:**

```bash
./scripts/bootstrap_venv.sh
cp config/templates/secrets.env.example config/secrets/secrets.env   # edit keys
./scripts/run.sh
```

Open `http://127.0.0.1:8765` (default). Put source audio in `ASSETS/input/`.

Details: [NORTH_STAR.md](NORTH_STAR.md) · [SETUP.md](SETUP.md)

## Commands

| Step | Command |
|------|---------|
| Setup (once) | `./scripts/bootstrap_venv.sh` |
| Launch GUI | `./scripts/run.sh` |
| Headless | `./scripts/run.sh --cli` |
| Rebuild GUI only | `MUX_REBUILD_GUI=1 ./scripts/run.sh` |

Runs and artifacts: `ASSETS/executions/exec_*`

## Layout

```text
scripts/bootstrap_venv.sh   # setup
scripts/run.sh              # launch
src/interview_mux/          # pipeline + API
frontend/                   # React GUI
config/                     # defaults + secrets
docs/                       # specs and prompts
tools/                      # CLI helpers (analysis, delivery, verify_master)
```
