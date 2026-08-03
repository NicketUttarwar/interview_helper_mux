# Podcast RSS hosting (The War Room)

**North star still ends at** `master/master.wav`. RSS publish is an optional Ship step after master.

## Architecture

- **Private S3** bucket holds `feed.xml`, `show/`, `catalog/`, `episodes/NNNN/`
- **CloudFront + OAC** is the only public origin (HTTP Range / seek works by default)
- App uploads with explicit **Content-Type** and invalidates `/feed.xml` on every feed update
- **Terraform** under [`terraform/`](../../terraform/) owns infra; **committed local state** is the inventory

## Where values live

| Kind | Where | Examples |
|------|--------|----------|
| Non-secret operator config | [`config/app.defaults.json`](../../config/app.defaults.json) `podcast` | `s3_bucket`, `aws_region`, `project_name`, show meta, S3 layout / file names |
| Credentials | [`config/secrets/secrets.env`](../../config/secrets/secrets.env) (**gitignored**) | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN` / `AWS_PROFILE` |
| AWS-derived runtime IDs | same `secrets.env` (synced by `tf-apply` / `sync_podcast_tf_secrets.sh`) | `PODCAST_CLOUDFRONT_DISTRIBUTION_ID`, `PODCAST_FEED_BASE_URL` |
| Infra inventory | [`terraform/state/terraform.tfstate`](../../terraform/state/terraform.tfstate) (**committed**) | Full resource graph |

Bucket name is **not** “owned” by secrets — keep `podcast.s3_bucket` in app.defaults aligned with Terraform `s3_bucket_name` (see `config/terraform.tfvars.example`). Optional `PODCAST_S3_BUCKET` in secrets is an override only.

## S3 layout (retrieveability)

```text
feed.xml
show/
  artwork.png
  show.json                 # seed
catalog/
  sequence.json             # next episode number
  by_source_hash.json       # re-publish V2/V3 history
  by_execution_id.json      # execution_id → s3_prefix (pipeline run lookup)
episodes/NNNN/              # one folder per published master / run
  episode.json              # title, description, guid=execution_id, urls, …
  description.txt           # plain description (search / human retrieve)
  audio.mp3                 # RSS enclosure
  master.wav                # optional archive (podcast.upload_master_wav)
  cover.png                 # ≥1400² square
  chapters.json             # optional
```

Public URLs: `{PODCAST_FEED_BASE_URL}/episodes/NNNN/…`

## Show channel

| Field | Source |
|-------|--------|
| Title / author / email / language / category / description | `podcast.*` in app.defaults |
| Artwork file | `podcast.show_artwork_path` → S3 `show/artwork.png` |

> Path note: on macOS, repo-root `assets/` case-folds into gitignored `ASSETS/`, so committed show art lives under `config/podcast/`.

## Operator steps

### 1 — Credentials + config

```bash
mkdir -p config/secrets
cp config/templates/secrets.env.example config/secrets/secrets.env
# set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (and OPENAI_API_KEY)
# confirm podcast.s3_bucket in config/app.defaults.json
cp config/terraform.tfvars.example config/terraform.tfvars   # keep s3_bucket_name in sync
```

### 2 — Create / update hosting

```bash
./scripts/tf-init.sh
./scripts/tf-plan.sh
./scripts/tf-apply.sh   # syncs CF ID + feed base URL into secrets.env
```

### 3 — Seed empty feed + show art

```bash
python scripts/seed_podcast_origin.py
```

### 4 — App

```bash
./scripts/bootstrap_venv.sh   # if .venv missing
./scripts/run.sh
```

Finish a pipeline → **G-Publish** → `podcast_publish`.

### 5 — Submit the feed

Open `{PODCAST_FEED_BASE_URL}/feed.xml`. Submit to Apple Podcasts Connect / Spotify.

## Pipeline stages (after `master_finalize`)

| Stage | Output |
|-------|--------|
| `episode_meta_build` | `publish/episode_meta.json` |
| `episode_cover_prompt_craft` | `publish/cover_prompt.json` |
| `podcast_encode_mp3` | `publish/audio.mp3` + `publish/master.wav` |
| `episode_cover_generate` | `publish/cover_candidates/*`, `cover_pick.json`, `cover.png`, `cover_meta.json` |
| `podcast_publish` | S3 episode folder + catalogs + feed + invalidation |

Same `source_audio_hash` re-publish appends ` V2`, ` V3`, … Folder is always a **new** `episodes/NNNN/`.

## Art style contract

See **[podcast-cover-theme.md](./podcast-cover-theme.md)** (authoritative). Summary:

- OpenAI `gpt-image-1` ×3 at `quality=high`, then flagship vision picks the **most brilliant** (lettered candidates disqualified)
- Motifs from post-master harvest only; show art = palette / low-fidelity style ref / fail-open
- Asterisks-only depicted text; without-clauses (no negative_prompt); cerulean + crimson every episode
- Local MLX cover path retired (`local_image.enabled=false`)

## Model routing (covers)

| Stage | Tier |
|-------|------|
| `episode_meta_build` | flagship chat |
| `episode_cover_prompt_craft` | flagship chat (draft→finalize) |
| `episode_cover_vision_pick` | flagship vision (among 3 candidates) |
| Images API | `podcast.cover_image.model` (pinned `gpt-image-1`) |

Intentional cost: 3 image gens + 1 vision compare per episode (optional 1 re-batch).

## Clean surface

| Keep | Do not keep |
|------|-------------|
| `terraform/` + committed tfstate | Imperative setup scripts / `infra/` |
| `podcast.*` in app.defaults for bucket + layout | Bucket name only in secrets |
| `scripts/tf-*.sh`, `sync_podcast_tf_secrets.sh`, seed | Publisher IAM keys from Terraform |
