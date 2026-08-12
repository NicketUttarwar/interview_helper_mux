# Terraform — The War Room podcast RSS stack

Private **S3** origin + **CloudFront OAC** for The War Room feed and episode media.

**Ops narrative:** [docs/cross-cutting/podcast-rss-hosting.md](../docs/cross-cutting/podcast-rss-hosting.md)  
**Pins:** [docs/cross-cutting/anchored-toolchain.md](../docs/cross-cutting/anchored-toolchain.md) (`terraform ~> 1.14.7`, AWS provider `~> 5.0`)

## Contract

| Do | Do not |
|----|--------|
| Use `./scripts/tf-*.sh` from the repo root | Call `terraform` raw against this tree (skips secrets load, session backup, var-file wiring) |
| Keep `config/terraform.tfvars` `s3_bucket_name` == `podcast.s3_bucket` in `config/app.defaults.json` | Put the bucket name only in secrets |
| Commit `terraform/state/terraform.tfstate` after successful applies | Commit `config/terraform.tfvars` or `config/secrets/secrets.env` |
| App publish / seed / invalidate via **boto3** + `secrets.env` | Require AWS CLI, `aws login`, or Console click-ops |

Region is fixed to **`us-east-1`**. Default logical base: **`the_war_room_001`**.

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
terraform/state/terraform.tfstate     ← live (committed)
terraform/state/session/latest.tfstate ← rolling backup (one file; updated after success)
```

- Every successful `scripts/tf-*.sh` run that touches state refreshes `session/latest.tfstate`.
- Restore before a command: `USE_LATEST_SESSION=1 ./scripts/tf-plan.sh` or `./scripts/tf-plan.sh --use-session` (flag is stripped before Terraform).

## Operator workflow

```bash
# 1) AWS creds in config/secrets/secrets.env
#    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (or AWS_PROFILE)
# 2) Align bucket name
cp config/terraform.tfvars.example config/terraform.tfvars
# edit s3_bucket_name to match config/app.defaults.json → podcast.s3_bucket

./scripts/tf-init.sh
./scripts/tf-plan.sh
./scripts/tf-apply.sh   # also upserts PODCAST_* into secrets.env

python scripts/seed_podcast_origin.py

# Destructive reset: remove every S3 object but preserve the bucket + CloudFront
./scripts/tf-empty-bucket.sh
```

Migrating `s3_bucket_name` recreates the origin bucket and retargets CloudFront **without** changing the distribution domain (feed URL stays stable).

Destroy (careful): `./scripts/tf-destroy.sh` — does not empty S3 objects for you.

## One-off: new RSS URL (archive old Apple feed)

Bucket renames alone **do not** change the CloudFront domain. To retire the live show URL for Apple and stand up a **new** `…/feed.xml` while keeping the old URL reachable as an archive:

```bash
./scripts/tf-rotate-rss-url.sh                 # preview, then yes/no
```

Details: [`terraform/archives/README.md`](archives/README.md). **Do not run until cutover.**

## Wrapper scripts (`scripts/tf-*.sh`)

All wrappers source `scripts/lib/terraform-common.sh` (load `secrets.env`, optional session restore, `-var-file`, arm64/Rosetta warnings, session backup).

| Script | Purpose |
|--------|---------|
| `tf-init.sh` | `terraform init` |
| `tf-plan.sh` | Plan |
| `tf-apply.sh` | Apply + `sync_podcast_tf_secrets.sh` |
| `tf-destroy.sh` | Destroy |
| `tf-empty-bucket.sh` | Delete all objects/versions from the managed S3 bucket; preserve infrastructure |
| `tf-rotate-rss-url.sh` | **One-off:** archive current CF feed URL (orphan from state, leave live), create a **new** S3+CloudFront feed URL — preview then yes/no |
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
