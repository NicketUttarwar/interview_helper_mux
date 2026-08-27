# Committed twin of the live Zero Shot origin (gitignored config/terraform.tfvars
# is still what default `./scripts/tf-*.sh` loads). New shows: add
# config/terraform/shows/<podcast_id>.tfvars and apply with
# `./scripts/tf-apply.sh --podcast-id <id>` so Zero Shot state is never loaded.
#
# After apply, record s3_bucket / cloudfront_distribution_id / feed_base_url
# in config/podcast/catalog.json (Start picker source of truth).

project_name   = "zero_shot_podcast_demo_001"
show_title     = "Zero Shot Podcast DEMO"
environment    = "prod"
s3_bucket_name = "zero-shot-podcast-demo-rss-001"

cloudfront_price_class = "PriceClass_200"
