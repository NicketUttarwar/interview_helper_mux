# Podcast RSS URL archives

Two different one-off operations write records here.

## Same-bucket CloudFront rotate (old URL deleted)

[`scripts/tf-rotate-cloudfront-url.sh`](../../scripts/tf-rotate-cloudfront-url.sh) writes `cf-url-rotate-*.json`:

- The **deleted** CloudFront feed URL (distribution is destroyed in AWS)
- The **replacement** distribution id / new `…/feed.xml`
- The **same** `s3_bucket` (objects kept)

After this script, `secrets.env` and `./scripts/invalidate_podcast_cf.sh` target the new URL.

## New origin (old URL left live)

[`scripts/tf-podcast-rss-origin.sh`](../../scripts/tf-podcast-rss-origin.sh) writes `rss-origin-*.json` (legacy name: `tf-rotate-rss-url.sh`):

- The **archived** CloudFront feed URL (left live in AWS; removed from Terraform state)
- The **replacement** bucket / project / new `podcast_guid` / new feed URL after apply

Do **not** destroy archived distributions if listeners or Apple still resolve the old URL.

```bash
# Same S3 bucket, new CloudFront URL (old URL dies)
./scripts/tf-rotate-cloudfront-url.sh

# New bucket + new CloudFront (old pair archived)
./scripts/tf-podcast-rss-origin.sh \
  --new-project the_war_room_002 \
  --new-bucket the-war-room-rss-002
```

Then submit the **new** `feed_url` from `./scripts/tf-output.sh` to Apple Podcasts if the listing must move. Wrappers print the Apple Podcasts Connect pass-through next to that URL (`https://podcastsconnect.apple.com/my-podcasts/new-feed?submitfeed=…`). **Notice:** Apple rejects an empty seed feed — publish at least one episode or a trailer first.
