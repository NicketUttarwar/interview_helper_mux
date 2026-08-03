# Setup — interview_helper_mux (v2)

Full fresh-env + RSS steps: **[README.md](README.md)**.

```bash
./scripts/bootstrap_venv.sh
mkdir -p config/secrets ASSETS/input
cp config/templates/secrets.env.example config/secrets/secrets.env   # OPENAI_API_KEY
./scripts/run.sh   # http://127.0.0.1:8765
```

**Podcast RSS (Terraform + boto3)** — bucket/layout in `config/app.defaults.json` (`podcast`); AWS creds + CF/feed in `secrets.env`. Infra via `scripts/tf-*.sh` (updates `terraform/state/`). App publish uses boto3 — **no AWS CLI / `aws login`**:

```bash
# AWS_* + OPENAI in config/secrets/secrets.env; confirm podcast.s3_bucket in app.defaults
./scripts/tf-init.sh && ./scripts/tf-plan.sh && ./scripts/tf-apply.sh
python scripts/seed_podcast_origin.py
./scripts/run.sh
# Optional recovery: ./scripts/invalidate_podcast_cf.sh
```

**North star:** [NORTH_STAR.md](NORTH_STAR.md) · RSS: [docs/cross-cutting/podcast-rss-hosting.md](docs/cross-cutting/podcast-rss-hosting.md)

Optional bootstrap flags: `BOOTSTRAP_SKIP_GUI=1`, `BOOTSTRAP_SKIP_VERIFY=1`

Optional run flags: `MUX_PRESERVE_SESSION=1`, `MUX_REBUILD_GUI=1`, `MUX_REFRESH_DEPS=1`, `MUX_SKIP_ASSETS_CLEANUP=1`

Operator journey: [docs/workflows/operator-journey.md](docs/workflows/operator-journey.md)
