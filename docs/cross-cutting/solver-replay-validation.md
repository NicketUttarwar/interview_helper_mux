# Solver replay validation

Offline replay of the deterministic solver (`src/interview_mux/solver.py`) against completed execution folders, standing in for the live full-auto run the forensics campaign forbids. Regenerate with `python tools/solver_replay.py`.

Generated: 2026-09-17T03:10:44Z

## Verdict

The bar is **D12** (plan §11): zero unexplained replay disagreements, and no regression against the driver. Those are the only two conditions, and both must hold.

**D12 gate NOT MET — promotion VETOED**

| D12 condition | Result | Detail |
|---|---|---|
| `no_unexplained_disagreements` | **VETO** | 1 unexplained choice divergence(s) of 14 total (13 attributed to mtime-only reconstruction); gate allows 0 |
| `no_regression_against_driver` | pass | 0 decision point(s) where the solver proposed a stage the driver's own history proves was not runnable (recorded `done`, not invalidated, never started again); gate allows 0 |

A veto here is the intended outcome of validating first. `MUX_SOLVER_AUTHORITATIVE` stays OFF.

### Retired bars — reported as context, never as vetoes

D12 dropped the 80% authority condition and the 5% structural-deferral condition. A solver that defers is *safe* — `authoritative_sequence` hands a deferred stage back to seed order — so what must be zero is being confidently **wrong**, not being quiet. Both numbers stay here as the progress signal for D10 (gate state on disk) and D11 (the strict ratchet), quoted against the bar that used to gate them so the scale is still legible. `promotion_verdict` cannot read them.

| Retired metric | Today | Retired bar | Status |
|---|---|---|---|
| `solver_has_authority` | 25.1% | 80.0% | reported only |
| `structural_deferral_bounded` | 26.0% | 5.0% | reported only |

### Corroborating evidence from outside the replay

- Live shadow mode on a fresh run measured the solver **confidently admissible on 2 of 72 stages, deferring on 35**, because only the `prepare` contract group is conformance-strict. That is an independent measurement of the same coverage problem this replay reports. Under D12 it is a progress signal, not a veto.
- **The fresh-run census is a tautology, not a measurement.** Exactly **37 of the 72 seed-order stages declare a concrete hard input and 35 do not** (verified against `load_contract` for all 72). That partition *is* the fresh-run census: on an empty run directory the 37 return `hard_input_missing` — the correct answer — and the 35 return `hard_inputs_undeclared`, which is an *unknown* and never an exclusion. `confident` means zero unknowns, so it needs at least one *satisfied* declared hard input, which no stage can have against an empty directory. Probing an empty run reproduces `0 confident / 35 deferred / 37 blocked` exactly. A statistic that can only take one value cannot rank solver quality, which is the concrete reason D12's retirement of the authority bar is right rather than merely convenient.

## Headline — coverage AND agreement, together

The solver could decide on its own authority at **25.1%** of 2498 decision points (627 of 2498). Across 12039 stage verdicts it was confidently admissible on **925** (7.7%), deferred on **6025** (50.0%), genuinely blocked on **2533** and **2556** were already complete.

Real disagreements: **1 unexplained** (of 14 choice divergences; 13 are attributable to mtime-only state reconstruction, see below), and **0** regression(s) against the driver. Those two numbers are the D12 gate. The coverage figure above is worthless as a gate in either direction — a solver with no justified opinion disagrees with nobody — which is why it is never quoted alone and no longer vetoes.

Separated out of the old headline: **590** dispatches were of a stage that was **already complete**. Those used to be counted as `skip` divergences and their verdicts as `blocked`, which is what made both numbers unreadable — a finished stage is neither blocked nor a disagreement.

## Corpus

- Execution folders scanned: **25** (hard cap 100; ranked pinned → reached `master/master.wav` → ledger size → recency)
- Folders contributing at least one dispatch: **25**
- Folders that reached `master/master.wav`: **11**
- Decision points replayed: **2498** of 2498 recorded

Recency alone selects nothing usable: the ~300 most recently written `exec_*` folders are all pytest fixtures whose ledger is under 2KB. The ranking therefore prefers runs that reached a master and runs with the most recorded history, with `exec_11871` pinned to the front.

| Run | Master | Points | Agree | Defer | Done | Skip | Choice | Authority |
|---|---|---|---|---|---|---|---|---|
| `exec_11871_d19c15b58ab4_20260916T002245Z` | yes | 299 | 22 | 74 | 47 | 155 | 1 | 74/299 |
| `exec_11630_d19c15b58ab4_20260915T033341Z` | yes | 184 | 21 | 44 | 48 | 71 | 0 | 32/184 |
| `exec_11130_d19c15b58ab4_20260909T213550Z` | yes | 149 | 15 | 51 | 16 | 66 | 1 | 45/149 |
| `exec_5196_d19c15b58ab4_20260903T184658Z` | yes | 128 | 12 | 61 | 44 | 8 | 3 | 33/128 |
| `exec_5410_d19c15b58ab4_20260906T142205Z` | yes | 130 | 16 | 61 | 36 | 17 | 0 | 17/130 |
| `exec_5399_d19c15b58ab4_20260904T012859Z` | yes | 84 | 18 | 55 | 9 | 2 | 0 | 18/84 |
| `exec_5404_d19c15b58ab4_20260905T215237Z` | yes | 97 | 15 | 49 | 30 | 3 | 0 | 15/97 |
| `exec_10066_d19c15b58ab4_20260909T050451Z` | yes | 112 | 17 | 52 | 33 | 10 | 0 | 17/112 |
| `exec_5570_d19c15b58ab4_20260907T214325Z` | yes | 87 | 16 | 44 | 20 | 7 | 0 | 16/87 |
| `exec_11160_d19c15b58ab4_20260911T001909Z` | yes | 109 | 15 | 40 | 34 | 17 | 3 | 27/109 |
| `exec_11550_d19c15b58ab4_20260911T232613Z` | yes | 78 | 14 | 45 | 15 | 2 | 2 | 26/78 |
| `exec_5409_d19c15b58ab4_20260906T031652Z` | no | 66 | 26 | 22 | 7 | 11 | 0 | 29/66 |
| `exec_11559_d19c15b58ab4_20260912T150346Z` | no | 87 | 19 | 34 | 8 | 26 | 0 | 29/87 |
| `exec_5402_d19c15b58ab4_20260905T045059Z` | no | 100 | 18 | 44 | 33 | 5 | 0 | 18/100 |
| `exec_5401_d19c15b58ab4_20260904T232903Z` | no | 85 | 17 | 48 | 14 | 6 | 0 | 17/85 |
| `exec_5583_d19c15b58ab4_20260908T034719Z` | no | 103 | 17 | 48 | 25 | 13 | 0 | 17/103 |
| `exec_5188_d19c15b58ab4_20260903T035354Z` | no | 94 | 16 | 30 | 40 | 7 | 1 | 25/94 |
| `exec_11165_d19c15b58ab4_20260911T165943Z` | no | 108 | 19 | 32 | 47 | 8 | 2 | 33/108 |
| `exec_9948_d19c15b58ab4_20260909T011823Z` | no | 102 | 25 | 21 | 5 | 51 | 0 | 72/102 |
| `exec_11136_d19c15b58ab4_20260910T212232Z` | no | 93 | 17 | 27 | 29 | 19 | 1 | 19/93 |
| `exec_5400_d19c15b58ab4_20260904T171837Z` | no | 88 | 17 | 52 | 12 | 7 | 0 | 17/88 |
| `exec_11676_d19c15b58ab4_20260915T181903Z` | no | 97 | 18 | 35 | 38 | 6 | 0 | 29/97 |
| `exec_5403_d19c15b58ab4_20260905T211126Z` | no | 12 | 0 | 4 | 0 | 8 | 0 | 0/12 |
| `exec_6652_d303811b8c84_20260908T225634Z` | no | 4 | 2 | 2 | 0 | 0 | 0 | 2/4 |
| `exec_5187_d19c15b58ab4_20260903T035354Z` | no | 2 | 0 | 2 | 0 | 0 | 0 | 0/2 |

## Deferral census

| Stage verdict | Count | Share |
|---|---|---|
| confidently admissible | 925 | 7.7% |
| deferred | 6025 | 50.0% |
| blocked | 2533 | |
| already complete | 2556 | |

`already complete` is split out of `blocked` on purpose. `evaluate_stage` returns `already_done` as a positive blocker (`solver.py:602`), which is the right answer for admissibility — a finished stage must not be offered — but counting it as *blocked* made the census say the pipeline seizes up as it succeeds, with the blocked count climbing toward 72 precisely because the run was finishing. `blocked` now means only "the solver proved this cannot run". **The underlying issue is in `solver.py`, which this tool does not own**: the correction is applied in the replay tool's classification (`verdict_is_complete`), keyed on `already_done` being the sole reason, so a genuinely blocked stage cannot be laundered into this bucket.

### Deferral causes, split by whether contract population can fix them

| Bucket | Unknowns | Meaning |
|---|---|---|
| `coverage` | 5012 | the contract does not yet declare enough; §4.3 population removes these |
| `structural` | 3132 | gate state that is not on disk, glob inputs, config-optional gates — population never removes these |

Structural share of all stage verdicts: **26.0%**. 5973 deferred verdicts belong to a contract group that is not yet conformance-strict.

| Unknown family | Bucket | Count |
|---|---|---|
| `hard_inputs_undeclared` | `coverage` | 5012 |
| `gate_auto_accept_pending` | `structural` | 2486 |
| `gate_may_pause` | `structural` | 646 |

### Whole-pipeline census (all dispatchable stages, sampled)

| Run | At | Confident | Deferred | Blocked | Already complete |
|---|---|---|---|---|---|
| `exec_11871_d19c15b58ab4_2026` | 2026-09-16T00:22:53Z | 0 | 35 | 37 | 0 |
| `exec_11871_d19c15b58ab4_2026` | 2026-09-16T01:20:11Z | 4 | 30 | 21 | 17 |
| `exec_11871_d19c15b58ab4_2026` | 2026-09-16T02:02:14Z | 1 | 24 | 13 | 34 |
| `exec_11871_d19c15b58ab4_2026` | 2026-09-16T05:50:23Z | 1 | 8 | 8 | 55 |
| `exec_11871_d19c15b58ab4_2026` | 2026-09-16T12:05:07Z | 1 | 0 | 2 | 69 |
| `exec_11630_d19c15b58ab4_2026` | 2026-09-15T03:33:51Z | 0 | 35 | 37 | 0 |
| `exec_11630_d19c15b58ab4_2026` | 2026-09-15T04:39:06Z | 5 | 22 | 19 | 26 |
| `exec_11630_d19c15b58ab4_2026` | 2026-09-15T06:20:30Z | 1 | 11 | 9 | 51 |
| `exec_11630_d19c15b58ab4_2026` | 2026-09-15T07:56:09Z | 1 | 9 | 8 | 54 |
| `exec_11130_d19c15b58ab4_2026` | 2026-09-09T21:36:04Z | 0 | 35 | 37 | 0 |
| `exec_11130_d19c15b58ab4_2026` | 2026-09-09T22:25:36Z | 6 | 25 | 20 | 21 |
| `exec_11130_d19c15b58ab4_2026` | 2026-09-09T22:40:34Z | 6 | 23 | 19 | 24 |
| `exec_11130_d19c15b58ab4_2026` | 2026-09-10T01:08:45Z | 1 | 15 | 6 | 50 |
| `exec_11130_d19c15b58ab4_2026` | 2026-09-10T05:45:03Z | 0 | 6 | 3 | 63 |
| `exec_5196_d19c15b58ab4_20260` | 2026-09-03T18:47:10Z | 0 | 35 | 37 | 0 |
| `exec_5196_d19c15b58ab4_20260` | 2026-09-03T19:24:40Z | 2 | 26 | 15 | 29 |
| `exec_5196_d19c15b58ab4_20260` | 2026-09-03T21:04:57Z | 1 | 24 | 5 | 42 |
| `exec_5196_d19c15b58ab4_20260` | 2026-09-03T22:24:09Z | 1 | 18 | 7 | 46 |
| `exec_5410_d19c15b58ab4_20260` | 2026-09-06T14:22:13Z | 0 | 35 | 37 | 0 |
| `exec_5410_d19c15b58ab4_20260` | 2026-09-06T14:57:39Z | 2 | 27 | 15 | 28 |

## Divergences — the classes, never merged

| Class | Meaning | Count |
|---|---|---|
| `agree` | solver would have dispatched the same stage | 392 |
| `defer` | solver declines to have an opinion (hollow contract, indeterminate gate) | 977 |
| `already_done` | the dispatched stage was **already complete** — not a disagreement about control flow at all | 590 |
| **`skip`** | solver proves the dispatched stage was not runnable *for some other reason* — it would have refused the dispatch. Agreement in spirit. | **525** |
| **`choice`** | solver would confidently have run a *different* stage — a real disagreement | **14** |

Agreement rate is 42.1% over the 931 points that produced an opinion about control flow (`agree` + `skip` + `choice`). `already_done` and `defer` are outside that denominator: neither is a statement about which stage should run next.

### Already-complete dispatches — held apart from `skip`

**590** dispatches re-ran a stage the solver could see was already finished. This is real driver behaviour worth reading, but it is not evidence about solver quality, so it is counted in neither the skip column nor the agreement rate. The `rerun` and `operator` sources are deliberate re-runs; a `conductor` or walk source is the thrash the campaign is chasing.

| Dispatch source | Count |
|---|---|
| `conductor` | 359 |
| `operator` | 189 |
| `rerun` | 42 |

This class is not inflatable by the reconstruction: a surviving `.stage_done` marker whose final mtime is at or before `T` did exist at `T`, so the mtime witness cannot invent a completion. Its failure mode is the opposite — a marker rewritten late reads as absent, which surfaces as a choice divergence instead.

Of those 14 choice divergences, **1** is unexplained and **13** name a preferred stage that produced no `kind=stage` ledger row anywhere in its run. For that second group the stage's done-timeline rests on the surviving `.stage_done` marker's mtime, which records the last write rather than the first, so the replay cannot distinguish a solver preference from a marker that was written early, invalidated and rewritten late. Both groups are listed.

### Regressions against the driver (D12 condition 2)

**0** of the 14 choice divergences are regressions. A regression is a decision point where the solver proposed a stage the *driver's own history proves* was not runnable: the ledger recorded it `done` at or before that instant, nothing invalidated it in between, and the driver never started it again for the rest of the run. That last clause is what makes it a proof — a driver that re-dispatches the stage minutes later has demonstrated the opposite, so its history settles nothing and the divergence is an ordering argument rather than a regression.

Only `choice` points can regress. At an `agree` point the solver's pick is the stage the driver ran, and at a `skip`, `already_done` or `defer` point the solver proposes nothing of its own.

**None.** This D12 condition passes.

### Skip divergences by blocker family

`already_done` no longer appears here — it has its own class above. What is left is the set of dispatches the solver would have refused on a real blocker.

| Blocker | Count |
|---|---|
| `door_refused` | 486 |
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

| Driver ran | Solver would have run | Count | Evidence | Regression |
|---|---|---|---|---|
| `boundary_topic_resplit` | `content_brief_reanchor` | 7 | mtime-only reconstruction | no |
| `missing_framing` | `content_brief_reanchor` | 4 | mtime-only reconstruction | no |
| `gap_framing_compose` | `content_brief_reanchor` | 1 | mtime-only reconstruction | no |
| `sound_design_palettes` | `content_brief_reanchor` | 1 | mtime-only reconstruction | no |
| `gap_framing_compose` | `missing_framing` | 1 | **unexplained** | no |

Unexplained, each needing its own account:

- `exec_5188_d19c15b58ab4_20260903T035354Z` seq 207 (2026-09-03T04:34:13Z): driver ran `gap_framing_compose`, solver would have run `missing_framing`

#### Traced to root cause

These accounts are hand-maintained and deliberately do not change the verdict — an explanation must never be able to promote anything.

- **`content_brief_reanchor`** — `content_brief_reanchor` executes as a substep and never emits a `kind=stage` ledger row, so the replay has no event evidence for it at all and falls back to its `.stage_done` marker mtime. In exec_11871 the session log shows the stage completing at 01:08:45Z while the surviving marker is stamped 02:02:56Z — written early, invalidated, rewritten late. Every decision point in between therefore sees a stage the walk had already retired, and the solver correctly calls it runnable from state that is wrong.
- **`missing_framing`** — **Traced, and it is not a replay artifact.** At exec_5188 seq 207 the driver's own ledger has `missing_framing` *done* eight seconds earlier (seq 198, 04:34:05Z) and never invalidated, yet the solver calls it confidently runnable. The cause is `stage_outputs_present('missing_framing')` → `stage_completion._research_thin_late_refuse`, which refuses every Shape/gap consumer while `research_shape_core_thin(ctx)` holds. `mastering_research_rollup` *had* run (seq 181–183, 04:30:27Z) and wrote a **thin** dossier, and it is dispatched exactly once in the whole run — so the thinness never clears, `missing_framing` reads incomplete for the rest of the phase, and `solver.stage_done` returns False on a stage that finished. Reproducing the seq-207 snapshot gives `stage_artifact_incompleteness('missing_framing')` = "research shape-core thin — resume mastering_research_rollup" from the run's real bytes: the dossier is present in the snapshot and thin, not a wrong revision. So this is a genuine defect in the completeness predicate, where an early gap-phase stage can never look complete until a research artifact is thick. The solver is arguably *right* — the driver reached the same conclusion three minutes later and re-dispatched `missing_framing` twice (seq 235, 245) — but it is still a real ordering disagreement, so it stays in the unexplained count. Because the driver did re-run the stage after the divergence, its history does not prove the stage was unrunnable, so this is **not** a D12 driver regression.

## What this replay cannot prove

- Artifact presence at time T is reconstructed from two witnesses: file mtime (the last write only) and the producing stage's ledger `done` row. The mtime witness misses artifacts overwritten later in the run; the producer witness covers most of that gap but reinstates the artifact's FINAL content, not the content it had at T. Content-sensitive sufficiency checks therefore see end-of-run bytes.
- run_meta.json is pinned to its final content from the first decision point, because posture, brain id and automation mode are run-level constants that cannot be recovered per-instant. Gate state that lives in run_meta (only the pre-clean enable does) is therefore seen as of end-of-run.
- The ownership matrix version seal is stripped from the replayed run_meta. Every run in the corpus was sealed against an older matrix, so leaving it in makes write_permitted refuse every output with `matrix_version_mismatch` — an artifact of replaying old runs against today's code, not a solver opinion.
- The dispatch door's attempt memo and no-delta guard read operator/dispatch_memo.json, which post-dates every run in the corpus. In replay they never fire, so door refusals are limited to ledger-counted caps and the skip class is an undercount on that axis.
- Lease and audio-serialisation state are wall-clock predicates. Replayed against a finished run they always read 'free', so the replay cannot exercise lease_held_by_gui or audio_serialize_inflight.
- Stage-done state comes from ledger done rows plus marker mtimes, reconciled against the invalidation log. A marker created, removed and recreated inside one decision interval is not recoverable.
- Stages that never produce a `kind=stage` ledger row — ones that run as a substep of another dispatch, through an API route, or are marked by a heal — have no event evidence at all, so their done-timeline is the marker mtime alone. Choice divergences naming such a stage are reported separately as reconstruction-limited rather than counted as disagreements, and the replay genuinely cannot settle them either way.
- Replay proves what the solver would have DECIDED given reconstructed state. It cannot prove what the run would have DONE: a refused dispatch changes every subsequent state, and the replay always follows the driver's actual path. No counterfactual trajectory is explored.
- The regression check (D12 condition 2) can only prove unrunnability one way: the driver recorded the stage `done`, nothing invalidated it, and it was never started again. A stage the driver never dispatched at all leaves no trace either way, so the check is sound but not exhaustive — zero regressions means 'the driver's history contradicts the solver nowhere it can speak', not 'the solver is right'.
- Deferral causes are read off StageVerdict.unknowns, which is the solver's own account of what it could not answer. A check the solver never attempts cannot appear as an unknown, so the census measures declared ignorance, not total ignorance.
