# Terraform — The War Room podcast RSS stack

Private **S3** origin + **CloudFront OAC** for The War Room feed and episode media.

**Ops narrative:** [docs/cross-cutting/podcast-rss-hosting.md](../docs/cross-cutting/podcast-rss-hosting.md)  
**Pins:** [docs/cross-cutting/anchored-toolchain.md](../docs/cross-cutting/anchored-toolchain.md) (`terraform ~> 1.14.7`, AWS provider `~> 5.0`)

## Contract

| Do | Do not |
|----|--------|
| Use `./scripts/tf-*.sh` from the repo root | Call `terraform` raw against this tree (skips secrets load, session backup, var-file wiring) |
| Keep `s3_bucket_name` aligned with `config/podcast/catalog.json` for that show | Put the bucket name only in secrets |
| Commit `terraform/state/terraform.tfstate` (Zero Shot) and `terraform/state/shows/<id>/terraform.tfstate` (other shows) after successful applies | Commit `config/terraform.tfvars` or `config/secrets/secrets.env` |
| App publish / seed / invalidate via **boto3** + catalog destinations + `secrets.env` creds | Require AWS CLI, `aws login`, Console click-ops, or creating AWS from the GUI |

Region is fixed to **`us-east-1`**. Default Zero Shot stack: **`zero_shot_podcast_demo_001`**.

The **GUI never creates AWS resources**. Start only picks a catalog show. New S3 + CloudFront origins are terminal (`./scripts/tf-*.sh --podcast-id <id>`), then recorded in [`config/podcast/catalog.json`](../config/podcast/catalog.json).

## Layout

| Path | Role |
|------|------|
| `versions.tf` | Terraform + AWS provider constraints |
| `backend.tf` | Local backend → `state/terraform.tfstate` |
| `providers.tf` | AWS provider |
| `variables.tf` / `locals.tf` | Inputs + derived names/tags |
| `s3.tf` / `bucket_policy.tf` | Private origin + OAC bucket policy |
| `cloudfront.tf` | Distribution (HTTP Range / seek) |
| `outputs.tf` | Bucket, CF id/domain, feed URLs |
| `state/terraform.tfstate` | **Committed** live inventory |
| `state/session/latest.tfstate` | Rolling backup after each successful wrapper run |

Variable values: copy [`config/terraform.tfvars.example`](../config/terraform.tfvars.example) → `config/terraform.tfvars` (gitignored). Override path with `TF_VAR_FILE`. Legacy `terraform/terraform.tfvars` still works with a warning.

## State model

```text
terraform/state/terraform.tfstate              ← Zero Shot live (committed; do not retarget)
terraform/state/session/latest.tfstate         ← Zero Shot rolling backup
terraform/state/shows/<podcast_id>/terraform.tfstate  ← other shows (committed after apply)
```

- Default wrappers (no `--podcast-id`) always use the Zero Shot state file above.
- `--podcast-id <id>` (when `<id>` is not `zero_shot_podcast_demo`) uses isolated state + `TF_DATA_DIR` so a plan/apply cannot load Zero Shot resources.
- Do **not** use `tf-podcast-rss-origin.sh` to add a second podcast — that archives the old origin out of state. Add a catalog row, write `config/terraform/shows/<id>.tfvars`, then `tf-init` / `tf-apply --podcast-id <id>`.

## Operator workflow

```bash
# 1) AWS creds in config/secrets/secrets.env
#    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (or AWS_PROFILE)
# 2) Align bucket name with catalog.json for this show
cp config/terraform.tfvars.example config/terraform.tfvars

./scripts/tf-init.sh
./scripts/tf-plan.sh
./scripts/tf-apply.sh   # writes destinations into catalog.json (Zero Shot also updates secrets fallback)

python scripts/seed_podcast_origin.py

# New show (does not touch Zero Shot state):
#   1. Add a row to config/podcast/catalog.json (id, title, artwork_path, …)
#   2. Write config/terraform/shows/<id>.tfvars
#   3. ./scripts/tf-init.sh --podcast-id <id>
#   4. ./scripts/tf-apply.sh --podcast-id <id>
#   5. python scripts/seed_podcast_origin.py --podcast-id <id>
#   6. Commit catalog.json + terraform/state/shows/<id>/terraform.tfstate

# Destructive reset: remove every S3 object but preserve the bucket + CloudFront
./scripts/tf-empty-bucket.sh
```

Migrating `s3_bucket_name` recreates the origin bucket and retargets CloudFront **without** changing the distribution domain (feed URL stays stable).

Destroy (careful): `./scripts/tf-destroy.sh` — does not empty S3 objects for you.

## One-off: new CloudFront RSS URL (same S3 bucket)

Bucket renames alone **do not** change the CloudFront domain. To **delete** the current `dxxxx.cloudfront.net/feed.xml` and create a new distribution in front of the **same** bucket:

```bash
./scripts/tf-rotate-cloudfront-url.sh          # preview, then type the current CF id
```

CloudFront-only: deletes the live CF RSS URL and creates a new distribution. **Never** empties, deletes, or recreates S3 (plan is refused if `aws_s3_bucket.origin` appears). Syncs secrets, rewrites `feed.xml` public hosts, invalidates the new CF, and prints Apple pass-through + Spotify paste URL. **Do not run until you intend to kill the old public feed.** Apple still requires ≥1 episode.

To stand up a **new bucket + new CloudFront** (archive the old pair, leave it live): `./scripts/tf-podcast-rss-origin.sh`. Details: [`terraform/archives/README.md`](archives/README.md). That script also prints the pass-through for the new feed.

## Wrapper scripts (`scripts/tf-*.sh`)

All wrappers source `scripts/lib/terraform-common.sh` (load `secrets.env`, optional session restore, `-var-file`, arm64/Rosetta warnings, session backup).

| Script | Purpose |
|--------|---------|
| `tf-init.sh` | `terraform init` |
| `tf-plan.sh` | Plan |
| `tf-apply.sh` | Apply + `sync_podcast_tf_secrets.sh` |
| `tf-destroy.sh` | Destroy |
| `tf-empty-bucket.sh` | Delete all objects/versions from the managed S3 bucket; preserve infrastructure |
| `tf-rotate-cloudfront-url.sh` | **One-off:** delete current CF feed URL, create a new distribution on the **same** S3 bucket; syncs secrets + invalidates `/feed.xml` |
| `tf-podcast-rss-origin.sh` | New **S3 + CloudFront** origin (archives the old pair, leaves it live) |
| `tf-refresh.sh` | Refresh state from AWS |
| `tf-output.sh` | Show outputs |
| `tf-show.sh` | Show state / saved plan |
| `tf-state.sh` | `terraform state …` |
| `tf-fmt-validate.sh` | `fmt` + `validate` |
| `tf-import.sh` | Import existing resources |
| `tf-graph.sh` | Dependency graph |
| `tf-console.sh` | Console |
| `tf-workspace.sh` | Workspaces |
| `tf-force-unlock.sh` | Force-unlock (local backend rarely needs this) |
| `tf-version.sh` | CLI version (does **not** load secrets) |

Related (not Terraform): `scripts/sync_podcast_tf_secrets.sh`, `scripts/seed_podcast_origin.py`, `scripts/sync_podcast_episodes.py`, `scripts/invalidate_podcast_cf.sh`.

Env knobs: `TF_QUIET=1`, `TF_TRACE=1`, `TF_VAR_FILE=…`, `USE_LATEST_SESSION=1`.

## Outputs → secrets

`tf-apply.sh` runs `sync_podcast_tf_secrets.sh`, which upserts:

- `PODCAST_CLOUDFRONT_DISTRIBUTION_ID`
- `PODCAST_FEED_BASE_URL`
- `AWS_DEFAULT_REGION` (from stack)

Bucket name stays in **`podcast.s3_bucket`** (`app.defaults.json`). Optional `PODCAST_S3_BUCKET` in secrets is an override only and must match Terraform.

## Apple Silicon note

If `tfenv` left an **x86_64** Terraform on arm64, or `.terraform/providers` has only `darwin_amd64`, plugin startup can time out. Wrappers warn; fix by reinstalling a native arm64 Terraform and re-running `./scripts/tf-init.sh` after removing `.terraform/providers`.

## Out of scope

Custom domain / ACM, multi-region, publisher IAM users from Terraform, AWS CLI as an operator dependency.
