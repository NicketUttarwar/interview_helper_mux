# interview_helper_mux

Turn a long-form interview recording into a **mastered podcast** (`master/master.wav`), with an optional **The War Room** RSS publish path (private S3 + CloudFront).

Details: [NORTH_STAR.md](NORTH_STAR.md) · [SETUP.md](SETUP.md) · [docs/cross-cutting/podcast-rss-hosting.md](docs/cross-cutting/podcast-rss-hosting.md)

---

## Fresh environment (once per machine)

Requires: macOS Apple Silicon recommended (local STT / image), Python 3.12, `ffmpeg`, Node (for GUI), Terraform `~> 1.14.7` if you will publish RSS.

```bash
# 1) Clone / enter repo
cd interview_helper_mux

# 2) Bootstrap core .venv + local MLX stacks (speech, LLM, image) + GUI
./scripts/bootstrap_venv.sh

# 3) Secrets
mkdir -p config/secrets ASSETS/input
cp config/templates/secrets.env.example config/secrets/secrets.env
# Edit config/secrets/secrets.env — set at least OPENAI_API_KEY

# 4) Put source interview audio in ASSETS/input/
#    e.g. ASSETS/input/interview.wav
```

Optional bootstrap flags: `BOOTSTRAP_SKIP_GUI=1`, `BOOTSTRAP_SKIP_VERIFY=1`

Episode covers use OpenAI Images (`podcast.cover_image`) — see [docs/cross-cutting/podcast-cover-theme.md](docs/cross-cutting/podcast-cover-theme.md).

---

## Daily launch

```bash
./scripts/run.sh
# open http://127.0.0.1:8765
```

| Step | Command |
|------|---------|
| Setup (once) | `./scripts/bootstrap_venv.sh` |
| Launch GUI | `./scripts/run.sh` |
| Headless | `./scripts/run.sh --cli` |
| Rebuild GUI only | `MUX_REBUILD_GUI=1 ./scripts/run.sh` |

Runs and artifacts: `ASSETS/executions/exec_*`

---

## The War Room RSS (optional — Terraform)

Infra lives under `terraform/` with **committed local state**. Bucket name and show/layout settings live in `config/app.defaults.json` → `podcast`. Credentials + CloudFront/feed URLs live in `config/secrets/secrets.env`. Default resource base: **`the_war_room_001`**.

### A — Create podcast hosting (S3 + CloudFront OAC)

```bash
# secrets.env must include AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (or AWS_PROFILE)
cp config/terraform.tfvars.example config/terraform.tfvars   # optional overrides
./scripts/tf-init.sh
./scripts/tf-plan.sh
./scripts/tf-apply.sh   # also upserts PODCAST_* into secrets.env
```

### B — Seed empty feed + show artwork

```bash
python scripts/seed_podcast_origin.py
```

### C — Run app and publish

```bash
./scripts/run.sh
```

Finish a pipeline → **G-Publish** → run `podcast_publish`.

### D — Submit the feed

Open `PODCAST_FEED_BASE_URL/feed.xml` and submit that URL to Apple Podcasts Connect (“Add a show with an RSS feed”) and Spotify for Podcasters.

Full ops: [docs/cross-cutting/podcast-rss-hosting.md](docs/cross-cutting/podcast-rss-hosting.md)

---

## Layout

```text
scripts/bootstrap_venv.sh          # fresh env
scripts/tf-*.sh                    # Terraform wrappers (podcast stack)
scripts/sync_podcast_tf_secrets.sh # outputs → PODCAST_* in secrets.env
scripts/seed_podcast_origin.py     # seed feed.xml + show art
scripts/run.sh                     # launch
terraform/                         # S3 + CloudFront OAC (state committed)
src/interview_mux/                 # pipeline + API
frontend/                          # React GUI
config/                            # defaults + secrets + podcast cover + tfvars.example
docs/                              # specs and prompts
tools/                             # CLI helpers
```
