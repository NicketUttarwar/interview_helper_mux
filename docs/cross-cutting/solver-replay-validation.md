# Solver replay validation

Offline replay of the deterministic solver (`src/interview_mux/solver.py`) against completed execution folders, standing in for the live full-auto run the forensics campaign forbids. Regenerate with `python tools/solver_replay.py`.

Generated: 2026-09-16T21:52:42Z

## Verdict

**Promotion: VETOED**

| Gate condition | Result | Detail |
|---|---|---|
| `no_unexplained_disagreements` | **VETO** | 1 unexplained choice divergence(s) of 14 total (13 attributed to mtime-only reconstruction); gate allows 0 |
| `solver_has_authority` | **VETO** | solver could decide on its own authority at 25.2% of decision points; gate needs 80.0% |
| `structural_deferral_bounded` | **VETO** | 26.3% of stage verdicts defer for a reason contract population cannot fix; gate allows 5.0% |

A veto here is the intended outcome of validating first. The headline below is deliberately two numbers, not one: agreement is only meaningful next to coverage.

## Headline — coverage AND agreement, together

The solver could decide on its own authority at **25.2%** of 2480 decision points (625 of 2480). Across 11922 stage verdicts it was confidently admissible on **923** (7.7%), deferred on **5969** (50.1%) and blocked **5030**.

Real disagreements: **1 unexplained** (of 14 choice divergences; 13 are attributable to mtime-only state reconstruction, see below). That number is worthless on its own — a solver with no justified opinion disagrees with nobody — which is why it is never quoted apart from the coverage figure above.

## Corpus

- Execution folders scanned: **100** (hard cap 100; ranked pinned → reached `master/master.wav` → ledger size → recency)
- Folders contributing at least one dispatch: **22**
- Folders that reached `master/master.wav`: **89**
- Decision points replayed: **2480** of 2480 recorded

Recency alone selects nothing usable: the ~300 most recently written `exec_*` folders are all pytest fixtures whose ledger is under 2KB. The ranking therefore prefers runs that reached a master and runs with the most recorded history, with `exec_11871` pinned to the front.

| Run | Master | Points | Agree | Defer | Skip | Choice | Authority |
|---|---|---|---|---|---|---|---|
| `exec_11871_d19c15b58ab4_20260916T002245Z` | yes | 299 | 22 | 74 | 202 | 1 | 74/299 |
| `exec_11630_d19c15b58ab4_20260915T033341Z` | yes | 184 | 21 | 44 | 119 | 0 | 32/184 |
| `exec_11130_d19c15b58ab4_20260909T213550Z` | yes | 149 | 15 | 51 | 82 | 1 | 45/149 |
| `exec_5196_d19c15b58ab4_20260903T184658Z` | yes | 128 | 12 | 61 | 52 | 3 | 33/128 |
| `exec_5410_d19c15b58ab4_20260906T142205Z` | yes | 130 | 16 | 61 | 53 | 0 | 17/130 |
| `exec_5399_d19c15b58ab4_20260904T012859Z` | yes | 84 | 18 | 55 | 11 | 0 | 18/84 |
| `exec_5404_d19c15b58ab4_20260905T215237Z` | yes | 97 | 15 | 49 | 33 | 0 | 15/97 |
| `exec_10066_d19c15b58ab4_20260909T050451Z` | yes | 112 | 17 | 52 | 43 | 0 | 17/112 |
| `exec_5570_d19c15b58ab4_20260907T214325Z` | yes | 87 | 16 | 44 | 27 | 0 | 16/87 |
| `exec_11160_d19c15b58ab4_20260911T001909Z` | yes | 109 | 15 | 40 | 51 | 3 | 27/109 |
| `exec_11550_d19c15b58ab4_20260911T232613Z` | yes | 78 | 14 | 45 | 17 | 2 | 26/78 |
| `exec_5409_d19c15b58ab4_20260906T031652Z` | no | 66 | 26 | 22 | 18 | 0 | 29/66 |
| `exec_11559_d19c15b58ab4_20260912T150346Z` | no | 87 | 19 | 34 | 34 | 0 | 29/87 |
| `exec_5402_d19c15b58ab4_20260905T045059Z` | no | 100 | 18 | 44 | 38 | 0 | 18/100 |
| `exec_5401_d19c15b58ab4_20260904T232903Z` | no | 85 | 17 | 48 | 20 | 0 | 17/85 |
| `exec_5583_d19c15b58ab4_20260908T034719Z` | no | 103 | 17 | 48 | 38 | 0 | 17/103 |
| `exec_5188_d19c15b58ab4_20260903T035354Z` | no | 94 | 16 | 30 | 47 | 1 | 25/94 |
| `exec_11165_d19c15b58ab4_20260911T165943Z` | no | 108 | 19 | 32 | 55 | 2 | 33/108 |
| `exec_9948_d19c15b58ab4_20260909T011823Z` | no | 102 | 25 | 21 | 56 | 0 | 72/102 |
| `exec_11136_d19c15b58ab4_20260910T212232Z` | no | 93 | 17 | 27 | 48 | 1 | 19/93 |
| `exec_5400_d19c15b58ab4_20260904T171837Z` | no | 88 | 17 | 52 | 19 | 0 | 17/88 |
| `exec_11676_d19c15b58ab4_20260915T181903Z` | no | 97 | 18 | 35 | 44 | 0 | 29/97 |

## Deferral census

| Stage verdict | Count | Share |
|---|---|---|
| confidently admissible | 923 | 7.7% |
| deferred | 5969 | 50.1% |
| blocked | 5030 | |

### Deferral causes, split by whether contract population can fix them

| Bucket | Unknowns | Meaning |
|---|---|---|
| `coverage` | 4956 | the contract does not yet declare enough; §4.3 population removes these |
| `structural` | 3132 | gate state that is not on disk, glob inputs, config-optional gates — population never removes these |

Structural share of all stage verdicts: **26.3%**. 5925 deferred verdicts belong to a contract group that is not yet conformance-strict.

| Unknown family | Bucket | Count |
|---|---|---|
| `hard_inputs_undeclared` | `coverage` | 4956 |
| `gate_auto_accept_pending` | `structural` | 2486 |
| `gate_may_pause` | `structural` | 646 |

### Whole-pipeline census (all dispatchable stages, sampled)

| Run | At | Confident | Deferred | Blocked |
|---|---|---|---|---|
| `exec_11871_d19c15b58ab4_2026` | 2026-09-16T00:22:53Z | 0 | 35 | 37 |
| `exec_11871_d19c15b58ab4_2026` | 2026-09-16T01:20:11Z | 4 | 30 | 38 |
| `exec_11871_d19c15b58ab4_2026` | 2026-09-16T02:02:14Z | 1 | 24 | 47 |
| `exec_11871_d19c15b58ab4_2026` | 2026-09-16T05:50:23Z | 1 | 8 | 63 |
| `exec_11871_d19c15b58ab4_2026` | 2026-09-16T12:05:07Z | 1 | 0 | 71 |
| `exec_11630_d19c15b58ab4_2026` | 2026-09-15T03:33:51Z | 0 | 35 | 37 |
| `exec_11630_d19c15b58ab4_2026` | 2026-09-15T04:39:06Z | 5 | 22 | 45 |
| `exec_11630_d19c15b58ab4_2026` | 2026-09-15T06:20:30Z | 1 | 11 | 60 |
| `exec_11630_d19c15b58ab4_2026` | 2026-09-15T07:56:09Z | 1 | 9 | 62 |
| `exec_11130_d19c15b58ab4_2026` | 2026-09-09T21:36:04Z | 0 | 35 | 37 |
| `exec_11130_d19c15b58ab4_2026` | 2026-09-09T22:25:36Z | 6 | 25 | 41 |
| `exec_11130_d19c15b58ab4_2026` | 2026-09-09T22:40:34Z | 6 | 23 | 43 |
| `exec_11130_d19c15b58ab4_2026` | 2026-09-10T01:08:45Z | 1 | 15 | 56 |
| `exec_11130_d19c15b58ab4_2026` | 2026-09-10T05:45:03Z | 0 | 6 | 66 |
| `exec_5196_d19c15b58ab4_20260` | 2026-09-03T18:47:10Z | 0 | 35 | 37 |
| `exec_5196_d19c15b58ab4_20260` | 2026-09-03T19:24:40Z | 2 | 26 | 44 |
| `exec_5196_d19c15b58ab4_20260` | 2026-09-03T21:04:57Z | 1 | 24 | 47 |
| `exec_5196_d19c15b58ab4_20260` | 2026-09-03T22:24:09Z | 1 | 18 | 53 |
| `exec_5410_d19c15b58ab4_20260` | 2026-09-06T14:22:13Z | 0 | 35 | 37 |
| `exec_5410_d19c15b58ab4_20260` | 2026-09-06T14:57:39Z | 2 | 27 | 43 |

## Divergences — the two classes, never merged

| Class | Meaning | Count |
|---|---|---|
| `agree` | solver would have dispatched the same stage | 390 |
| `defer` | solver declines to have an opinion (hollow contract, indeterminate gate) | 969 |
| **`skip`** | solver proves the dispatched stage was not runnable — it would have refused the dispatch. Agreement in spirit. | **1107** |
| **`choice`** | solver would confidently have run a *different* stage — a real disagreement | **14** |

Of those 14 choice divergences, **1** are unexplained and **13** name a preferred stage that produced no `kind=stage` ledger row anywhere in its run. For that second group the stage's done-timeline rests on the surviving `.stage_done` marker's mtime, which records the last write rather than the first, so the replay cannot distinguish a solver preference from a marker that was written early, invalidated and rewritten late. Both groups are listed.

### Skip divergences by blocker family

| Blocker | Count |
|---|---|
| `already_done` | 590 |
| `door_refused` | 478 |
| `hard_input_missing` | 39 |

Examples:

- `transcript_review_build` @ seq 51 — `door_refused:max_invokes_per_identity`
- `transcript_review_build` @ seq 57 — `door_refused:max_invokes_per_identity`
- `transcript_review_build` @ seq 62 — `door_refused:max_invokes_per_identity`
- `transcript_review_build` @ seq 67 — `door_refused:max_invokes_per_identity`
- `transcript_review_build` @ seq 73 — `door_refused:max_invokes_per_identity`
- `transcript_review_build` @ seq 78 — `door_refused:max_invokes_per_identity`
- `transcript_review_build` @ seq 85 — `door_refused:max_invokes_per_identity`
- `transcript_review_build` @ seq 90 — `door_refused:max_invokes_per_identity`

### Choice divergences (real disagreements)

| Driver ran | Solver would have run | Count | Evidence |
|---|---|---|---|
| `boundary_topic_resplit` | `content_brief_reanchor` | 7 | mtime-only reconstruction |
| `missing_framing` | `content_brief_reanchor` | 4 | mtime-only reconstruction |
| `gap_framing_compose` | `content_brief_reanchor` | 1 | mtime-only reconstruction |
| `sound_design_palettes` | `content_brief_reanchor` | 1 | mtime-only reconstruction |
| `gap_framing_compose` | `missing_framing` | 1 | **unexplained** |

Unexplained, each needing its own account:

- `exec_5188_d19c15b58ab4_20260903T035354Z` seq 207 (2026-09-03T04:34:13Z): driver ran `gap_framing_compose`, solver would have run `missing_framing`

#### Traced to root cause

These accounts are hand-maintained and deliberately do not change the verdict — an explanation must never be able to promote anything.

- **`content_brief_reanchor`** — `content_brief_reanchor` executes as a substep and never emits a `kind=stage` ledger row, so the replay has no event evidence for it at all and falls back to its `.stage_done` marker mtime. In exec_11871 the session log shows the stage completing at 01:08:45Z while the surviving marker is stamped 02:02:56Z — written early, invalidated, rewritten late. Every decision point in between therefore sees a stage the walk had already retired, and the solver correctly calls it runnable from state that is wrong.
- **`missing_framing`** — `stage_outputs_present('missing_framing')` routes through `stage_artifact_incompleteness`, which reads the CONTENT of `understanding/gap_evaluations.json`. The replay can restore that file's existence from the producer's ledger `done` row but only ever has its end-of-run bytes, so a content-sensitive completeness check is being asked about the wrong revision. Note the driver re-dispatched `missing_framing` twice within four minutes of the divergence (exec_5188 seq 235 and 245), so the solver's preference was not obviously wrong — but the replay cannot settle it, and it is left in the unexplained count rather than argued away.

## What this replay cannot prove

- Artifact presence at time T is reconstructed from two witnesses: file mtime (the last write only) and the producing stage's ledger `done` row. The mtime witness misses artifacts overwritten later in the run; the producer witness covers most of that gap but reinstates the artifact's FINAL content, not the content it had at T. Content-sensitive sufficiency checks therefore see end-of-run bytes.
- run_meta.json is pinned to its final content from the first decision point, because posture, brain id and automation mode are run-level constants that cannot be recovered per-instant. Gate state that lives in run_meta (only the pre-clean enable does) is therefore seen as of end-of-run.
- The ownership matrix version seal is stripped from the replayed run_meta. Every run in the corpus was sealed against an older matrix, so leaving it in makes write_permitted refuse every output with `matrix_version_mismatch` — an artifact of replaying old runs against today's code, not a solver opinion.
- The dispatch door's attempt memo and no-delta guard read operator/dispatch_memo.json, which post-dates every run in the corpus. In replay they never fire, so door refusals are limited to ledger-counted caps and the skip class is an undercount on that axis.
- Lease and audio-serialisation state are wall-clock predicates. Replayed against a finished run they always read 'free', so the replay cannot exercise lease_held_by_gui or audio_serialize_inflight.
- Stage-done state comes from ledger done rows plus marker mtimes, reconciled against the invalidation log. A marker created, removed and recreated inside one decision interval is not recoverable.
- Stages that never produce a `kind=stage` ledger row — ones that run as a substep of another dispatch, through an API route, or are marked by a heal — have no event evidence at all, so their done-timeline is the marker mtime alone. Choice divergences naming such a stage are reported separately as reconstruction-limited rather than counted as disagreements, and the replay genuinely cannot settle them either way.
- Replay proves what the solver would have DECIDED given reconstructed state. It cannot prove what the run would have DONE: a refused dispatch changes every subsequent state, and the replay always follows the driver's actual path. No counterfactual trajectory is explored.
- Deferral causes are read off StageVerdict.unknowns, which is the solver's own account of what it could not answer. A check the solver never attempts cannot appear as an unknown, so the census measures declared ignorance, not total ignorance.
