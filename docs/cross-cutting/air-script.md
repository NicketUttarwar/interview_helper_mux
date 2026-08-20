# Air-script — Shape realization on `mastering_plan`

Air-script is the **Realization** half of the Mastering Process. It lives **on** `mastering/mastering_plan.json` (`air_script`, `story_spine`, `circumstance_card`, `sonic_scenes`, `sonic_opportunities`) — never as a sidecar `master/air_script.json` beside an ignored plan.

Without it, delivery concatenates every approved part (layup + glue + every-Nth beds). With it, EDL emits only the paper-edit, and music scores those beats.

Canon parent: [mastering-process.md](./mastering-process.md).

## Why it belongs in mastering

Best listen = native nuggets + grounded synthetic conversation + a composed musical score, mutated as one ensemble. Air-script is the paper-edit of **what airs** (natives, VO seats, omits, montage moves). Musical architecture is the other Shape axis: opportunity hunt → `sonic_scenes` → motif-family compose → ducked mix.

Fail-open only when the plan is absent or `mastering.air_script.enable` is false.

## Conflict precedence

1. Confirmed `mastering_plan.air_script` beats + `story_spine` + `sonic_scenes`
2. NLE locks (order among remaining members; cannot restuff Pass A omits)
3. Hard-keeps / locked speaker volleys
4. `selection.json` as **palette only**
5. EDL / mix as executor, never editor

## Two passes (same plan object)

| Pass | Stage | Writes |
|------|-------|--------|
| A | `air_script_compose` (after ranking) | membership, order, `cold_open`, `energy_curve`, `story_spine`, `circumstance_card`, omits |
| B | `air_script_seams` (after layup freeze) | per-seam `montage_move`, VO seats, `air_script.vo_seats`, `sonic_opportunities`, `sonic_scenes` |

`auto_pack` may not restuff Pass A omits. Layup still composes **candidates**; Pass B chooses which VO seats air. EDL emits only those seats. Synthetic episode orientation airs only when the native open does not already greet or introduce.

Pass B publishes `air_script.vo_seats` (`seated_line_ids`, `omitted_line_ids`, `orientation_id`) on the same plan object. `edl_narrative_qc`, G1 synthesize, and recovery heals **subscribe** to that contract — they must not rebuild `gap_framing_plan` from unfiltered `interviewer_lines`.

## Montage moves

`native_handoff`, `vo_then_clip`, `clip_then_react_vo`, `music_face_out`, `air_breathe`, `cold_open_hook`, `information_package`, `episode_close`.

Consecutive `vo_then_clip` is a smell. Beds may duck under `native_handoff`. Do not stack clone VO + stinger + glue on one seam.

`native_handoff` and `air_breathe` are **dressed** joins: the assembly ledger stamps `glue_waived=native_handoff` (or `air_breathe`) and junction / `seam_glue` must not mint canned pair-specific bridges onto those destinations.

## Story-success contract

A first-time listener must retell who was talking, the thesis, the main claims, and why the ending landed.

1. At most one orientation, early, and only when native hosts do not already intro. Never re-welcome.
2. Know-entering / know-leaving on every beat.
3. Setup before payoff; unpaid cold-open tease fails.
4. Chronology default; few thematic jumps.
5. One host: native interviewer already framing → `native_handoff`.
6. VO earns the seat (unlock next native or recover a needed excluded fact).
7. Talking-points spine is the retell checklist.
8. First mention of people/places/terms unlocked.
9. Passion islands sticky.
10. Withhold ≠ drop the ladder.

`story_followability` is a listen-delight dimension. Confusion remutates before mix.

## Musical architecture

Deterministic opportunity hunter (pause-tails, spine scene edges, energy_curve, orientation/package/outro, post-VO air) writes `sonic_opportunities`. Compose places existing motif-family stems onto those rows — abundant constant-level underbeds (Shape band ~0.55–0.88) plus motif / stinger / resolve / outro. **Music-only** (no whoosh/foley). Dry only for `source_music_risk` / skip-underscore / panel overlap.

Show audio stays instrumental. Speech still wins the duck. Lane exclusivity in `music_lane.py` stays.
