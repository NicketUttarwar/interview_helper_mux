# Seam autopsy and bounded recovery

The seam autopsy is the authoritative listenability-decision layer between mix
and final master. It diagnoses every speech-to-speech join, records the allowed
repair grammar, and proves that repairs were committed to both the EDL and the
rendered assembly.

## Contract

`master/seam_autopsy.json` contains:

- one stable decision per seam (`pair_continuity_hash`)
- continuity, information, music, density, and finishability scores
- glue, music, and synthetic-voice budgets
- the worst seams for recovery prioritization
- commitment status: `pending`, `committed`, `diverged`, or `stale`

`master/render_ledger.json` binds the audible assembly to the exact EDL hash and
records every realized clip. A repair may be called `applied` only when its
result can be found in the current EDL and the assembly was rendered after that
EDL. `master_finalize` blocks on any other commitment status.

## Native and synthetic speech

Native selection is frozen before `synthetic_framing_plan`. The LLM receives a
bounded `understanding/synthetic_context_packet.json` containing selected
native clips, narrative/mastering intent, coverage, gap evidence, reorder seams,
speaker policy, and available autopsy risks.

Synthetic count, placement, text, and duration are dynamic:

- duration ratio: 40–200% of the anchor native segment
- 20–80% input share is guidance, not a quota
- dense guest answers and impact lines are protected
- source-contiguous seams prefer native extension or intentional air
- canned bridge fallback is forbidden

## Music

Consecutive per-segment cues using the same motif are rendered as one scene bed
with fades only at scene boundaries. Cold-open and outro cues are rebound to the
first and last selected native anchors. Music and punctuators cannot attack
inside synthetic-voice windows.

**`prefer_contiguous_beds` (`mastering.music_continuity.prefer_contiguous_beds`,
default `true`)** is the single flag both the mix and the autopsy honor for
"one scene bed, not a hard restart at every cut":

- At mix time, `sound_design.flow1_overlays_from_sdp` merges adjacent
  same-`asset_id` `under_segment` cues into one `under_segment_span` scene bed
  crossfaded only at the span edges (`music_continuity.scene_crossfade_ms`).
- At autopsy time, `seam_autopsy.score_seam` mirrors the flag onto
  `music_hint.continue_bed` for every source-contiguous seam. When the flag is
  off (or a contiguous seam otherwise won't carry its bed across), the seam
  gets an honest `music_hard_edge` risk code — a real, non-decorative signal
  that continuous speech audio will get an audible bed cut/restart, not a
  hard-coded pass.
- `music_hard_edge` feeds `scores.music_completeness` in `build_autopsy`
  (`1.0` when no seam carries the risk, `0.5` otherwise) and, downstream,
  `listen_delight._sonic_weave` (one of the seven ship-gating delight
  dimensions — see below): both read the real risk-code list rather than
  assuming continuity, so a config change that breaks contiguous-bed behavior
  shows up as a lower score instead of being silently masked.

## Recovery lifecycle

There are at most **two full remediation runs**:

1. Identify every currently visible broken piece.
2. Write one `master/failure_review.json`.
3. Write one `master/remediation_plan.json` covering every piece.
4. Apply all independent actions in dependency order.
5. Rebuild the EDL and assembly, then rescan.

Run 2 is allowed only for the complete residual set after run 1. A third run is
forbidden. Remaining failures stop loudly and block finalize, MP3 encoding, and
podcast packaging. Each batch appends failure/fix outcomes to
`ASSETS/remediation_learning.jsonl`.

## Final quality

After `master/master.wav` is created, post-master quality always runs. It writes:

- `master/post_master_quality.json`
- `master/listener_scorecard.json`

Publish is allowed only when seam commitment, junction residuals, feel audit
(available after ≤2 LLM attempts; OH-J1), render ledger, mastering-plan
authority, master existence, and listener scorecard floors all pass
(`overall≥0.90`; dimensions ≥0.90 except `synthetic_fit≥0.85`).

`junction_feel_audit_unavailable` after retry is a blocking reason. Music fade
repairs commit `sound_design/placement_adjustments.json` and patch SDP
`crossfade_ms` so remasters keep soft fades. Phrase recovery prefers extend (in-clip) → transcript+LLM **thought-complete recut** (traverse following same-speaker speech, cut at the complete thought, leave leftover independent) → cut → exclude (true micros only). Whole-segment `merge_micro` absorb is not used for hanging native ends.
Learning rows in `ASSETS/remediation_learning.jsonl` bias the next
`plan_all_fixes` action choice when the source hash or failure codes match.

## Listen delight dimensions

`listen_delight.run_listen_delight_audit` (`mastering/listen_delight_audit.json`)
is the **authoritative ship gate** ahead of `post_master_quality` (config:
`mastering.listen_delight`) — see NORTH_STAR.md. Its seven dimensions each read
real artifacts already on disk, falling back to soft defaults only when an
artifact is missing (never to mask a real signal that *is* present):

| Dimension | Floor | Source signal |
|-----------|-------|----------------|
| `nugget_retention` | `0.80` | Selected duration vs `delivery_brief` ideal pack target (~65% of source; prefer concise / at-or-under ideal) |
| `cut_integrity` | `0.85` | `junction_snip_qa.json` critical residual findings |
| `conversation_fit` | `0.85` | `bridge_completeness.json` missing/stub bridge counts, else mode-consistency soft score |
| `sonic_weave` | `0.85` | `seam_autopsy.json` `scores.music_completeness`, else a live count of `music_hard_edge` risk codes across seams |
| `mode_coherence` | `0.80` | `mode_consistency_report.ok` (when `require_mode_consistency`) |
| `finishability` | `0.80` | Mode consistency + gap-line presence + `cut_integrity` |
| `recommendability` | `0.75` | Gap-line presence / narrative mode + mode consistency |

`sonic_weave` is this module's direct downstream consumer: it is only as
honest as `music_completeness`, which is only as honest as the
`music_hard_edge` risk code documented under **Music** above. Overall floor
`0.90` (mean of the seven); `authoritative` mode hard-stops both
`listen_delight_audit` and the `post_master_quality` re-check on failure —
`advisory` writes the same scored artifact without blocking.
