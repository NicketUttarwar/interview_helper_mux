# Information packages + episode close

Canon for mid-episode **information packages** and the always-on musical **episode close**. Strategy: [mastering-process.md](./mastering-process.md) · Shape: [narrative-mode-and-montage.md](./narrative-mode-and-montage.md) · VO content: [nugget-layup-system.md](./nugget-layup-system.md).

## Ownership

| Concern | Owner |
|---------|--------|
| Whether/where a mid-body package fires (≤2, high bar) | Shape stage `information_package_plan` → `mastering_plan.information_packages` |
| What the dense before-VO says | Nugget Layup (`detail_budget=dense` on package targets) |
| Episode musical close after last native | Always `mastering_plan.episode_close` → SDP `theme_outro` cue |

Never call mid-body packages “soft start” or “cold open.” Episode-level `cold_open` remains show-open only.

## Information packages (optional, fail-closed)

- Cap: **0–2** per episode (`mastering.shape.information_packages.max_per_episode`).
- Modes: `shadow` (audit only, default) → `commit_music_vo` → `commit_with_regroup` (`allow_regroup` stays false until Phase 2).
- Objective gates: novelty, necessity, magnitude, uplift; final seam reserved for episode close.
- Music: `theme_chapter_resolve` face-out after `after_segment_id` (never mid-body `theme_outro` / `theme_cold_open`).
- VO: single before-line per target via Nugget Layup; seam_glue placeholders suppressed when layup present.

## Episode close (always)

```json
"episode_close": {
  "music": {
    "required": true,
    "role": "theme_outro",
    "placement": "after_last_native",
    "fade_out": "gentle_long",
    "fade_out_ms": 2200,
    "may_underscore_last_native_tail": true
  }
}
```

- Required musical cadence after the last native with a long gentle fade (`bookend_fade_out_ms` / `episode_close.fade_out_ms`).
- Independent of package `enable` / `mode` — package kill-switch does **not** disable outro.
- If a package would collide with the final bookend, the package is rejected; outro wins.

## Artifacts

- `mastering/shape/information_package_candidates.json`
- `mastering/shape/information_packages_audit.json`
- Plan fields on `mastering/mastering_plan.json`

## Config

`mastering.shape.information_packages.*` and `mastering.shape.episode_close.*` — see [config-keys.md](./config-keys.md).
