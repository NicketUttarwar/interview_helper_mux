# Podcast RSS URL archives

Records written by [`scripts/tf-rotate-rss-url.sh`](../../scripts/tf-rotate-rss-url.sh).

Each `rss-rotate-*.json` captures:

- The **archived** CloudFront feed URL (left live in AWS; removed from Terraform state)
- The **replacement** bucket / project / new `podcast_guid` / new feed URL after apply

Do **not** destroy archived distributions if listeners or Apple still resolve the old URL.

## Rotate later (do not run until cutover)

```bash
# Preview then yes/no prompt
./scripts/tf-rotate-rss-url.sh

# Optional naming overrides
./scripts/tf-rotate-rss-url.sh \
  --new-project the_war_room_002 \
  --new-bucket the-war-room-rss-002
```

Then submit the **new** `feed_url` from `./scripts/tf-output.sh` to Apple Podcasts as a new show.