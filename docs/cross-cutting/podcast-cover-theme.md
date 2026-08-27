# Podcast cover theme — OpenAI excellence cascade

War Room episode covers are **OpenAI-only**. Show art (`config/podcast/ZERO_SHOT_PODCAST_LOGO_nicket_uttarwar_demo_DEMO.png`; legacy: `config/podcast/the-war-room-cover.legacy.png`) supplies **palette / low-fidelity style reference / fail-open** — never required props (no default map, mic, or emblem).

Authoritative theme: [`config/podcast/cover_theme.json`](../../config/podcast/cover_theme.json).

## Resolution contract

| Spec | Value |
|------|--------|
| Target output | **3000 × 3000** JPEG (Apple preferred maximum; Spotify-compatible) |
| Apple hard minimum | 1400 × 1400 (publish fails below this) |
| Generation size | OpenAI square (`1024x1024`) then LANCZOS upscale |
| Feed / S3 object | `cover.jpg` (episode), `show/artwork.jpg` (channel) |
| Config | `podcast.cover_image.min_output_px=3000`, `output_format=jpeg` |

## Cascade

1. **Flagship chat** — `episode_meta_build` (title/description).
2. **Flagship chat** — `episode_cover_prompt_craft` draft → finalize (max 2 attempts). Harvest motifs from post-master artifacts; rich prompt anatomy; **objects/symbols only (never person likeness)**; asterisks-only depicted text; without-clauses (no Images `negative_prompt`).
3. **gpt-image ×3** — same finalized prompt, `quality=high` (Context7 pin: `gpt-image-1`, size `1024x1024`, upscale to **3000px JPEG**). Optional `images.edit` style ref with `input_fidelity=low`.
4. **Flagship vision** — rank three candidates; **brilliance is the primary pick criterion**; hard-disqualify readable letters/words and person likeness. Winner → `publish/cover.jpg`.
5. At most **one** re-batch of three if all hard-fail; else show-art fail-open (also converted to 3000² JPEG).

Cost tradeoff (3× image + 1 vision, optional re-batch) is intentional.

## Prompt anatomy

Hero subject (object/symbol only) · supporting motifs · composition · palette locks (cerulean **and** crimson) · material/finish · lighting · asterisks text policy · without-clauses (including no person likeness).

## Artifacts

| Path | Role |
|------|------|
| `publish/cover_prompt.json` | Final prompt, motifs, without-clauses, checklist, reject reasons |
| `publish/cover_candidates/0.jpg` … | Three candidates (JPEG) |
| `publish/cover_pick.json` | Ranking, brilliance scores, disqualifications, `winner_index` |
| `publish/cover.jpg` | Winner (or show fallback) |
| `publish/cover_meta.json` | Model, size, quality, candidate_count, winner, pick model |

## Config

See `podcast.cover_theme_path` and `podcast.cover_image` in [`config/app.defaults.json`](../../config/app.defaults.json). Model routing: `models.stages.episode_meta_build`, `episode_cover_prompt_craft`, `episode_cover_vision_pick` → **flagship**.

## Prompts

- [`docs/prompts/publishing/episode-cover-prompt.system.txt`](../prompts/publishing/episode-cover-prompt.system.txt) — craft  
- [`docs/prompts/publishing/episode-cover-vision-pick.system.txt`](../prompts/publishing/episode-cover-vision-pick.system.txt) — pick  
- [`docs/prompts/publishing/episode-meta.system.txt`](../prompts/publishing/episode-meta.system.txt) — meta  
- [`docs/prompts/publishing/podcast-show-description.system.txt`](../prompts/publishing/podcast-show-description.system.txt) — **legacy Flow 3 only**
