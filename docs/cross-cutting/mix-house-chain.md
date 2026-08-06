# Mix house chain (policy)

Audacity-class **order**, not a full DAW UI. Speech / [speaker volleys](./volley-glossary.md) first.

1. Preclean / hygiene (optional DeepFilter, or FFmpeg `afftdn` fallback)  
2. Edit — keep speaker volleys intact; fades at edges  
3. Per-speaker level match (`mix.per_speaker_level_match`, median LUFS/RMS, ±6 dB clamp)  
4. Place VO at volley boundaries / framing-before-impact  
5. Place beds under active speaker volleys; stingers at hinges  
6. Duck — speech-wins envelope sidechain under volleys (`mix.sidechain_duck`; static fallback)  
7. Glue / safety limiter (`master.safety_limiter_*` → FFmpeg `alimiter`)  
8. Loudnorm → `master/master.wav` (−16 LUFS podcast)  
9. QC — `verify_master`, intelligibility, soundscape remux capped  

## Speech-wins ducking / VO↔native harmony (Plan 4)

Step 6 is **speech-wins** by construction, not just by name: `sidechain_duck.envelope_duck`
follows a speech-RMS envelope (attack 20 ms / release 200 ms defaults) and attenuates the
bed under *any* active voice on the timeline — recorded/native speech **and** synthetic VO
pickups alike, since both render through the same speech clip path before beds overlay.
There is no separate "VO mode" vs "native mode" duck depth; the same envelope-follower
contract keeps beds out of the way of whichever voice is speaking, so a VO bridge and the
native answer either side of it duck identically. `pause_ride_db` (`mix.sidechain_duck` /
`mix.pause_ride_db`) is the one intentional asymmetry: beds are allowed to ride *up* during
intentional air (post-VO gaps, pauses) precisely because no voice — native or synthetic —
is competing for the band there. Per-speaker level match (step 3, `speaker_level_match.py`)
runs *before* ducking so the envelope follower sees a level-matched speech signal rather
than chasing per-speaker gain differences.

## Bed coverage / hinge stinger — Shape-owned soft bands (Plan 4)

`bed_coverage` (**0.28–0.88** of selection duration) and `hinge_stinger_coverage`
(**0.3–1.0** of chapter/topic hinges) are **Shape-owned soft bands** —
`listenability_guards._DEFAULTS`, documented in
[config-keys.md](./config-keys.md#creative_deliverylistenability_guards) — not a remux-theater
target that post-mix verify chases by any means necessary. They describe the range a
well-produced, Shape-driven master already falls into across many source types. The bands
are wide on purpose: a dense, bed-heavy documentary and a sparse two-hander are both
legitimate outcomes of the same Shape engine: [mastering-process.md](./mastering-process.md).

**Soundscape verify must not game coverage by seeding per-clip beds.** `soundscape_verify.py`
measures the *real* plan (`_estimate_bed_coverage` sums actual planned bed duration over
actual selection duration — no synthetic inflation) and, only when short of the floor,
delegates to `artifact_repairs.repair_sound_design_plan`'s palette/quartile-anchored bed
seeding — capped at `soundscape.remediation.max_remux_cycles` (default 2) — which itself
prefers extending an already-bedded neighbor segment (contiguous, honest scene bed) over
scattering a fresh disjoint per-clip bed, when `prefer_contiguous_beds` is set (default).
If every residual failure after that ladder is *only* a minimum-coverage shortfall (not a
maximum overshoot or an intelligibility miss), `run_soundscape_verify` ships a loud warning
instead of forcing `fail_closed` — see [soundscape-policy.md](./soundscape-policy.md#remediation-ladder-capped).

## `prefer_contiguous_beds` (Plan 4, wired)

`mastering.music_continuity.prefer_contiguous_beds` (default `true`) is honored in two
places that must agree:

- **Mix time** — `sound_design.flow1_overlays_from_sdp` merges consecutive per-segment
  `under_segment` cues that share an `asset_id` and sit on adjacent selected segments into
  one `under_segment_span` scene bed, crossfading only at the *scene* boundary
  (`music_continuity.scene_crossfade_ms`, default 1800 ms) instead of hard-fading and
  restarting the bed at every segment cut.
- **Autopsy time** — `seam_autopsy.score_seam`'s `music_hint.continue_bed` mirrors the same
  flag: a source-contiguous seam gets `continue_bed=True` (soft scene crossfade,
  `crossfade_ms=1500`) when the flag is on; turning it off makes every contiguous seam a
  `music_hard_edge` risk (a hard bed restart across continuous speech), which is reflected
  honestly in `music_completeness` / `listen_delight`'s `sonic_weave` dimension rather than
  a hard-coded pass — see [seam-autopsy.md](./seam-autopsy.md#music).

See [soundscape-policy.md](./soundscape-policy.md) · [local-audio-stack.md](./local-audio-stack.md) · [config-keys.md](./config-keys.md#masteringmusic_continuity).
