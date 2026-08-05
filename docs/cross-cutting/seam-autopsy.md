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
`crossfade_ms` so remasters keep soft fades. Phrase recovery prefers
extend → same-speaker `merge_micro` → cut → exclude (true micros only).
Learning rows in `ASSETS/remediation_learning.jsonl` bias the next
`plan_all_fixes` action choice when the source hash or failure codes match.
