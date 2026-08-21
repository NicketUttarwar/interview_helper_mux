# Plan (evaluation only) — VO shape + own-IP CTA omit

Status: **implemented** (0.1.0 flagship + host execute). Synced with the Cursor plan.

## Decision owner

**Flagship, on the fly.** Homunculus 0.1.0 conductor packs nested flagship packets (`full_master_ranking`, mine, compose, opener). Those calls judge CTA drop / recut / cover / per-line VO shape for **this tape**. Host executes (drop, re-cut, QC). Media-IP CTA speech-acts stay LLM-first (no whole-master POV lock).

**Sponsor bumper hard-omit:** host keyword omit for `sponsored by` / `presented by` / `brought to you by` / `powered by` / `in partnership with` (plus existing subscribe/buy-now phrases). Editorial `exclude_rationales` and ranking excludes with monetization/sponsor reasons **must leave the locked air order** via `apply_cta_judgments` leftovers + `apply_editorial_omits` + editorial-aware `reconcile_ordered_vs_excluded`.

Hard after admit: never-touch dropped words; quota-exempt; never name old IP.

## Product rules

- **Opener only:** first synthetic VO, if it is an opener, defaults to **third person**.
- **Later clone lines:** decide shape **per line** in `nugget_layup_compose` while writing `text`.
- **Hybrid hinge OK:** third person may end with “Let’s hear X explain why Y works,” or after a host-CTA hole “Let’s hear our conversation.”
- **CTA drop:** flagship speech-act on this tape for media-IP pitches. Keep business/finance talk. **Never name** the old show/course/brand in cover VO.
- **Sponsor / underwriter bumpers:** hard-omit on the sponsor phrase list above; also drop when ranking/Shape/editorial rationale says sponsor/promo. Put ids in `excluded_segment_ids` **and** omit from `ordered_segment_ids`.
- **Only drop media-IP pitch when it is clearly a pitch.** If the model is unsure (story vs pitch), **leave the clip on the master** (unless a sponsor hard-omit phrase hits).
- **Any speaker.** If it is that kind of media-IP pitch or sponsor bumper, drop it whether host or guest said it.
- **Usually 0–N per tape.** List every clearly flagged pitch. Mixed story+pitch in any clip still uses the complete-thought partition re-cut path (new `segment_id`s and all related metadata). Must-keep bits stay on admitted **clean children** only — parent hard-keep never skips prune.
- **Re-cut cannot be done cleanly** (bad cuts, too short, error): **drop the whole clip**.

## Collision resolutions

| Collision | Your rule |
|-----------|-----------|
| Nugget system wants to save dropped-tape words | **Never touch** the CTA clip. Cover uses other tape only. |
| ~40% before-VO quota | CTA drop(s) are **exempt**. |
| Clone VO right before your next native clip | **Allow.** Flag, **rerun** text+voice in third person (“Let’s hear our conversation”). This rerun **does not count** toward the 3-try cap. |
| Later code rewrites the line into a generic question | Compose’s third-person + “let’s hear…” **wins**. |
| Native length floor | Drops are fine. |
| Pitch mixed into a longer story clip / must-keep | **Re-cut.** New ids; drop only the pitch piece. Story remainder keeps (or gets) a new id. |
| Re-cut fails | **Drop the whole clip.** |
| Pitch was the first thing on tape | **Flagship LLM** chooses leftover story first **or** third-person opener VO. |
| Dual membership (ordered + excluded) | **Editorial exclude wins** (leave air order). Non-editorial noise: air order wins. |
| Operator UI | **Logs only.** No extra GUI step. |
| 0.0.0 vs 0.1.0 | **0.1.0 only.** Original slider walk unchanged. |
