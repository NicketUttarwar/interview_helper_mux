# Podcast RSS hosting (The War Room)

**North star still ends at** `master/master.wav`. RSS publish is an optional Ship step after master.

## AWS management contract (repo-wide)

| Concern | Mechanism | Not used |
|---------|-----------|----------|
| Create / change / destroy S3 + CloudFront | **Terraform** via [`scripts/tf-*.sh`](../../scripts/) — updates committed [`terraform/state/terraform.tfstate`](../../terraform/state/terraform.tfstate) | AWS Console click-ops, imperative setup scripts, AWS CLI |
| Sync CF ID + feed base into secrets | `./scripts/tf-apply.sh` → [`sync_podcast_tf_secrets.sh`](../../scripts/sync_podcast_tf_secrets.sh) | Manual copy from Console |
| Upload episode / seed / invalidate / sync | **boto3** in Python (`podcast_rss/s3_publish.py`, `podcast_rss/sync_assets.py`) using `config/secrets/secrets.env` | `aws s3`, `aws cloudfront`, `aws login` |

Operators put `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (or `AWS_PROFILE`) in `secrets.env`. **Never** assume `aws login` or AWS CLI is installed.

## Architecture

- **Private S3** bucket holds `feed.xml`, `show/`, `catalog/`, `episodes/NNNN/`
- **CloudFront + OAC** is the only public origin (HTTP Range / seek works by default)
- App uploads with explicit **Content-Type** and invalidates `/feed.xml` on every feed update (publish + seed)
- Manual recovery: [`scripts/invalidate_podcast_cf.sh`](../../scripts/invalidate_podcast_cf.sh)
- **Terraform** under [`terraform/`](../../terraform/) owns infra; **committed local state** is the inventory
- Bucket renames update the CloudFront **origin** but keep the **same distribution URL**

## Where values live

| Kind | Where | Examples |
|------|--------|----------|
| Non-secret operator config | [`config/app.defaults.json`](../../config/app.defaults.json) `podcast` | `s3_bucket`, `season`, `show_website`, show meta, S3 layout / file names |
| Credentials | [`config/secrets/secrets.env`](../../config/secrets/secrets.env) (**gitignored**) | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN` / `AWS_PROFILE` |
| AWS-derived runtime IDs | same `secrets.env` (synced by `tf-apply` / `sync_podcast_tf_secrets.sh`) | `PODCAST_CLOUDFRONT_DISTRIBUTION_ID`, `PODCAST_FEED_BASE_URL` |
| Infra inventory | [`terraform/state/terraform.tfstate`](../../terraform/state/terraform.tfstate) (**committed**) | Full resource graph |

Keep `podcast.s3_bucket` aligned with Terraform `s3_bucket_name` (see `config/terraform.tfvars.example`). Optional `PODCAST_S3_BUCKET` in secrets is an override only and must match.

## S3 layout (retrieveability)

```text
feed.xml
show/
  artwork.jpg               # 3000² JPEG show art
  show.json
catalog/
  sequence.json             # next episode number
  by_source_hash.json       # re-publish V2/V3 history
  by_execution_id.json      # execution_id → s3_prefix
episodes/NNNN/              # one folder per published master / run
  episode.json
  description.txt
  audio.mp3                 # stereo enclosure
  master.wav                # always uploaded (public via CF)
  cover.jpg                 # 3000² JPEG
  chapters.json             # Podcasting 2.0 timed chapters
```

Public URLs: `{PODCAST_FEED_BASE_URL}/episodes/NNNN/…`  
Feed URL: `{PODCAST_FEED_BASE_URL}/feed.xml`

## Show channel

| Field | Source |
|-------|--------|
| Title / author / email / language / explicit | `podcast.*` |
| Website `<link>` | `podcast.show_website` (default `https://nicketuttarwar.com/`) |
| Category | `Business` → nested `Entrepreneurship` |
| Type | `episodic` |
| Season (items) | `podcast.season` (default `1`; edit app.defaults to advance) |
| Artwork | `podcast.show_artwork_path` → S3 `show/artwork.jpg` (3000² JPEG) |
| Podcast GUID | `podcast.podcast_guid` (stable UUID) |

## Operator steps

### 1 — Credentials + config

```bash
mkdir -p config/secrets
cp config/templates/secrets.env.example config/secrets/secrets.env
# set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (and OPENAI_API_KEY)
# confirm podcast.s3_bucket == the-war-room-rss-001
cp config/terraform.tfvars.example config/terraform.tfvars   # keep s3_bucket_name in sync
```

### 2 — Create / update hosting (keep CloudFront URL)

```bash
./scripts/tf-init.sh
./scripts/tf-plan.sh
./scripts/tf-apply.sh   # syncs CF ID + feed base URL into secrets.env
```

Migrating `s3_bucket_name` recreates the origin bucket and retargets CloudFront **without** changing the distribution domain.

### 3 — Seed empty feed + show art

```bash
python scripts/seed_podcast_origin.py   # uploads + invalidates /feed.xml
```

### 4 — App

```bash
./scripts/bootstrap_venv.sh   # if .venv missing
./scripts/run.sh
```

Finish pipeline through master → **G-Publish**:

1. **Prepare package for this run** — clears the gate and runs `episode_meta_build`…`podcast_publish` **locally** (writes `publish/package_ready.json`; no S3).
2. **Upload all ready packages to S3** — ASSETS-wide sync of complete packages (GUI or script below). Never deletes S3 objects; skips `execution_id`s already in `catalog/by_execution_id.json`.
3. **Skip** — decline packaging for this run.

```bash
python scripts/sync_podcast_episodes.py           # upload all ready packages
python scripts/sync_podcast_episodes.py --dry-run # list would-upload / skip
```

### 5 — Submit the feed (once)

Open `{PODCAST_FEED_BASE_URL}/feed.xml` (full URL, not the base alone).

1. **Apple Podcasts Connect** — Add show → paste feed URL → verify owner email → submit for review  
2. **Spotify for Podcasters** — Add podcast → paste the same feed URL  

Later episodes: directories poll the feed; no re-submit unless the feed URL changes.

### Recovery — CloudFront invalidation

```bash
./scripts/invalidate_podcast_cf.sh              # /feed.xml
./scripts/invalidate_podcast_cf.sh --wait
./scripts/invalidate_podcast_cf.sh --all-media  # feed + episodes/* + show/*
```

## Pipeline stages (after `master_finalize`)

| Stage | Output |
|-------|--------|
| `episode_meta_build` | `publish/episode_meta.json` |
| `episode_cover_prompt_craft` | `publish/cover_prompt.json` |
| `podcast_encode_mp3` | stereo `publish/audio.mp3` + `publish/master.wav` |
| `episode_cover_generate` | candidates + `publish/cover.jpg` (3000²) |
| `podcast_publish` | Local package finalize (`package_ready.json`) — **no S3** |

S3 upload is **not** a pipeline stage. Use `scripts/sync_podcast_episodes.py` or G-Publish → Upload all. Same `source_audio_hash` re-publish (new execution) appends ` V2`, ` V3`, …. Folder is always a **new** `episodes/NNNN/` for unknown `execution_id`s; known ids are skipped (no duplicate folders). Sync never deletes remote objects; unchanged file sizes skip PutObject.

## Art style contract

See **[podcast-cover-theme.md](./podcast-cover-theme.md)** (authoritative). Summary:

- OpenAI `gpt-image-1` ×3 at `quality=high`, upscale to **3000×3000 JPEG**
- Vision pick for brilliance; show-art fail-open
- Apple accepts 1400–3000; we target the preferred maximum (3000)

## Model routing (covers)

| Stage | Tier |
|-------|------|
| `episode_meta_build` | flagship chat |
| `episode_cover_prompt_craft` | flagship chat (draft→finalize) |
| `episode_cover_vision_pick` | flagship vision (among 3 candidates) |
| Images API | `podcast.cover_image.model` (pinned `gpt-image-1`) |

## Clean surface

| Keep | Do not keep |
|------|-------------|
| `terraform/` + committed tfstate | Imperative setup scripts / `infra/` |
| `podcast.*` in app.defaults for bucket + layout | Bucket name only in secrets |
| `scripts/tf-*.sh`, `sync_podcast_tf_secrets.sh`, seed, `sync_podcast_episodes.py`, `invalidate_podcast_cf.sh` | Publisher IAM keys from Terraform |
| Same CloudFront distribution URL across bucket renames | Custom domain (out of scope) |
