# Publishing & RSS package (Ship)

**LLM stack:** [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md) · [model-routing.md](../../cross-cutting/model-routing.md)  
**Hosting:** [podcast-rss-hosting.md](../../cross-cutting/podcast-rss-hosting.md) · [terraform/README.md](../../../terraform/README.md)  
**Covers:** [podcast-cover-theme.md](../../cross-cutting/podcast-cover-theme.md)

Optional Ship path after `master_finalize`. North star remains `master/master.wav`. Flow 3 show-description pipeline was **removed** — see [v2/drop-manifest.md](../../v2/drop-manifest.md).

## Intent

Build a **local episode package** (meta, cover, stereo MP3, chapters) under `publish/`, then optionally sync **this run's** package to the private S3 origin (CloudFront serves the feed). Sibling executions under `ASSETS/executions/` are never uploaded by the app.

## When it runs

After `master_finalize`, operator chooses at **G-Publish**:

| Action | Effect |
|--------|--------|
| **Prepare package for this run** | Runs `episode_meta_build` … `podcast_publish` locally — writes `publish/package_ready.json`; **no S3** |
| **Upload this run to S3** | Syncs only this execution (`POST …/g-publish/sync` or `python scripts/sync_podcast_episodes.py --execution-id …`) |
| **Skip** | Decline packaging for this run |

Gate copy: [operator-gates.md](../../workflows/operator-gates.md).

## Stage sequence

| Order | Stage key | Model tier | Output |
|-------|-----------|------------|--------|
| 1 | `episode_meta_build` | **flagship** | `publish/episode_meta.json` |
| 2 | `episode_cover_prompt_craft` | **flagship** | `publish/cover_prompt.json` |
| 3 | `podcast_encode_mp3` | — | stereo `publish/audio.mp3` + `publish/master.wav` |
| 4 | `episode_cover_generate` | Images + vision | candidates + `publish/cover.jpg` (3000²) |
| 5 | `podcast_publish` | — | Local finalize (`package_ready.json`) — **no S3** |

Module: `src/interview_mux/stages/podcast_publish.py`.

## S3 sync (not a pipeline stage)

```bash
python scripts/sync_podcast_episodes.py --execution-id exec_…   # this run only
python scripts/sync_podcast_episodes.py --execution-id exec_… --dry-run
python scripts/sync_podcast_episodes.py --all                   # explicit bulk
```

Additive only — never deletes remote objects; skips known `execution_id`s. App/GUI/e2e always scope to the current run. Same `source_audio_hash` re-publish appends ` V2`, ` V3`, ….

## Heritage (removed)

Pre-v2 Flow 3 (`REMOVED_podcast_show_description` / `REMOVED_export_show_description`) produced a ~200-word show blurb. That pipeline and G2 flow picker are deleted. Episode titles/descriptions for RSS now come from `episode_meta_build` under G-Publish.
