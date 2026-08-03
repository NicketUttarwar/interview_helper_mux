# Podcast cover theme — OpenAI excellence cascade

War Room episode covers are **OpenAI-only**. Show art (`config/podcast/the-war-room-cover.png`) supplies **palette / low-fidelity style reference / fail-open** — never required props (no default map, mic, or emblem).

Authoritative theme: [`config/podcast/cover_theme.json`](../../config/podcast/cover_theme.json).

## Cascade

1. **Flagship chat** — `episode_meta_build` (title/description).
2. **Flagship chat** — `episode_cover_prompt_craft` draft → finalize (max 2 attempts). Harvest motifs from post-master artifacts; rich prompt anatomy; asterisks-only depicted text; without-clauses (no Images `negative_prompt`).
3. **gpt-image ×3** — same finalized prompt, `quality=high` (Context7 pin: `gpt-image-1`, size `1024x1024`, upscale to ≥1400px). Optional `images.edit` style ref with `input_fidelity=low`.
4. **Flagship vision** — rank three candidates; **brilliance is the primary pick criterion**; hard-disqualify readable letters/words. Winner → `publish/cover.png`.
5. At most **one** re-batch of three if all hard-fail; else show-art fail-open.

Cost tradeoff (3× image + 1 vision, optional re-batch) is intentional.

## Prompt anatomy

Hero subject · supporting motifs · composition · palette locks (cerulean **and** crimson) · material/finish · lighting · asterisks text policy · without-clauses.

## Artifacts

| Path | Role |
|------|------|
| `publish/cover_prompt.json` | Final prompt, motifs, without-clauses, checklist, reject reasons |
| `publish/cover_candidates/0.png` … `2.png` | Three candidates |
| `publish/cover_pick.json` | Ranking, brilliance scores, disqualifications, `winner_index` |
| `publish/cover.png` | Winner (or show fallback) |
| `publish/cover_meta.json` | Model, size, quality, candidate_count, winner, pick model |

## Config

See `podcast.cover_theme_path` and `podcast.cover_image` in [`config/app.defaults.json`](../../config/app.defaults.json). Model routing: `models.stages.episode_meta_build`, `episode_cover_prompt_craft`, `episode_cover_vision_pick` → **flagship**.

## Prompts

- [`docs/prompts/publishing/episode-cover-prompt.system.txt`](../prompts/publishing/episode-cover-prompt.system.txt) — craft  
- [`docs/prompts/publishing/episode-cover-vision-pick.system.txt`](../prompts/publishing/episode-cover-vision-pick.system.txt) — pick  
- [`docs/prompts/publishing/episode-meta.system.txt`](../prompts/publishing/episode-meta.system.txt) — meta  
- [`docs/prompts/publishing/podcast-show-description.system.txt`](../prompts/publishing/podcast-show-description.system.txt) — **legacy Flow 3 only**
