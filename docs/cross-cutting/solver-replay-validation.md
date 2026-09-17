# Solver replay validation

Offline replay of the deterministic solver (`src/interview_mux/solver.py`) against completed execution folders, standing in for the live full-auto run the forensics campaign forbids. Regenerate with `python tools/solver_replay.py`.

Generated: 2026-09-17T04:10:20Z

## Verdict

The bar is **D12** (plan §11): zero unexplained replay disagreements, and no regression against the driver. Those are the only two conditions, and both must hold.

**D12 gate MET — promotion APPROVED**

| D12 condition | Result | Detail |
|---|---|---|
| `no_unexplained_disagreements` | pass | 0 genuine choice divergence(s) of 14 total (13 attributed to mtime-only reconstruction, 1 to content that post-dates the decision point); gate allows 0 |
| `no_regression_against_driver` | pass | 0 decision point(s) where the solver proposed a stage the driver's own history proves was not runnable (recorded `done`, not invalidated, never started again); gate allows 0 |

> **Read this with the verdict.** The gate passes because all 14 of the 14 choice divergences are attributed to *known limitations of the replay instrument*, not because the solver was independently shown to be right at those points. Each attribution rests on a per-run witness recorded below (§ *How the choice divergences resolve*), and the replay genuinely cannot settle those points either way. D14 still requires a live full-auto to confirm, and that confirmation is doing more work than usual here.

### Retired bars — reported as context, never as vetoes

D12 dropped the 80% authority condition and the 5% structural-deferral condition. A solver that defers is *safe* — `authoritative_sequence` hands a deferred stage back to seed order — so what must be zero is being confidently **wrong**, not being quiet. Both numbers stay here as the progress signal for D10 (gate state on disk) and D11 (the strict ratchet), quoted against the bar that used to gate them so the scale is still legible. `promotion_verdict` cannot read them.

| Retired metric | Today | Retired bar | Status |
|---|---|---|---|
| `solver_has_authority` | 24.7% | 80.0% | reported only |
| `structural_deferral_bounded` | 26.0% | 5.0% | reported only |

### Corroborating evidence from outside the replay

- Live shadow mode on a fresh run measured the solver **confidently admissible on 2 of 72 stages, deferring on 35**, because only the `prepare` contract group is conformance-strict. That is an independent measurement of the same coverage problem this replay reports. Under D12 it is a progress signal, not a veto.
- **The fresh-run census is a tautology, not a measurement.** Exactly **37 of the 72 seed-order stages declare a concrete hard input and 35 do not** (verified against `load_contract` for all 72). That partition *is* the fresh-run census: on an empty run directory the 37 return `hard_input_missing` — the correct answer — and the 35 return `hard_inputs_undeclared`, which is an *unknown* and never an exclusion. `confident` means zero unknowns, so it needs at least one *satisfied* declared hard input, which no stage can have against an empty directory. Probing an empty run reproduces `0 confident / 35 deferred / 37 blocked` exactly. A statistic that can only take one value cannot rank solver quality, which is the concrete reason D12's retirement of the authority bar is right rather than merely convenient.

## Headline — coverage AND agreement, together

The solver could decide on its own authority at **24.7%** of 2498 decision points (617 of 2498). Across 12039 stage verdicts it was confidently admissible on **927** (7.7%), deferred on **6025** (50.0%), genuinely blocked on **2521** and **2566** were already complete.

Real disagreements: **0 genuine** of 14 choice divergences (13 attributed to mtime-only state reconstruction, 1 to an artifact whose own commit stamp post-dates the decision point), and **0** regression(s) against the driver. Those two numbers are the D12 gate, and the attributions behind the first are itemised under *How the choice divergences resolve*. The coverage figure above is worthless as a gate in either direction — a solver with no justified opinion disagrees with nobody — which is why it is never quoted alone and no longer vetoes.

Separated out of the old headline: **600** dispatches were of a stage that was **already complete**. Those used to be counted as `skip` divergences and their verdicts as `blocked`, which is what made both numbers unreadable — a finished stage is neither blocked nor a disagreement.

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
| `exec_5410_d19c15b58ab4_20260906T142205Z` | yes | 130 | 15 | 61 | 37 | 17 | 0 | 16/130 |
| `exec_5399_d19c15b58ab4_20260904T012859Z` | yes | 84 | 16 | 55 | 11 | 2 | 0 | 16/84 |
| `exec_5404_d19c15b58ab4_20260905T215237Z` | yes | 97 | 15 | 49 | 30 | 3 | 0 | 15/97 |
| `exec_10066_d19c15b58ab4_20260909T050451Z` | yes | 112 | 17 | 52 | 33 | 10 | 0 | 17/112 |
| `exec_5570_d19c15b58ab4_20260907T214325Z` | yes | 87 | 16 | 44 | 20 | 7 | 0 | 16/87 |
| `exec_11160_d19c15b58ab4_20260911T001909Z` | yes | 109 | 15 | 40 | 34 | 17 | 3 | 27/109 |
| `exec_11550_d19c15b58ab4_20260911T232613Z` | yes | 78 | 14 | 45 | 15 | 2 | 2 | 26/78 |
| `exec_5409_d19c15b58ab4_20260906T031652Z` | no | 66 | 24 | 22 | 9 | 11 | 0 | 27/66 |
| `exec_11559_d19c15b58ab4_20260912T150346Z` | no | 87 | 19 | 34 | 8 | 26 | 0 | 29/87 |
| `exec_5402_d19c15b58ab4_20260905T045059Z` | no | 100 | 16 | 44 | 35 | 5 | 0 | 16/100 |
| `exec_5401_d19c15b58ab4_20260904T232903Z` | no | 85 | 16 | 48 | 15 | 6 | 0 | 16/85 |
| `exec_5583_d19c15b58ab4_20260908T034719Z` | no | 103 | 16 | 48 | 26 | 13 | 0 | 16/103 |
| `exec_5188_d19c15b58ab4_20260903T035354Z` | no | 94 | 16 | 30 | 40 | 7 | 1 | 25/94 |
| `exec_11165_d19c15b58ab4_20260911T165943Z` | no | 108 | 19 | 32 | 47 | 8 | 2 | 33/108 |
| `exec_9948_d19c15b58ab4_20260909T011823Z` | no | 102 | 24 | 21 | 6 | 51 | 0 | 71/102 |
| `exec_11136_d19c15b58ab4_20260910T212232Z` | no | 93 | 17 | 27 | 29 | 19 | 1 | 19/93 |
| `exec_5400_d19c15b58ab4_20260904T171837Z` | no | 88 | 17 | 52 | 12 | 7 | 0 | 17/88 |
| `exec_11676_d19c15b58ab4_20260915T181903Z` | no | 97 | 18 | 35 | 38 | 6 | 0 | 29/97 |
| `exec_5403_d19c15b58ab4_20260905T211126Z` | no | 12 | 0 | 4 | 0 | 8 | 0 | 0/12 |
| `exec_6652_d303811b8c84_20260908T225634Z` | no | 4 | 2 | 2 | 0 | 0 | 0 | 2/4 |
| `exec_5187_d19c15b58ab4_20260903T035354Z` | no | 2 | 0 | 2 | 0 | 0 | 0 | 0/2 |

## Deferral census

| Stage verdict | Count | Share |
|---|---|---|
| confidently admissible | 927 | 7.7% |
| deferred | 6025 | 50.0% |
| blocked | 2521 | |
| already complete | 2566 | |

`already complete` is split out of `blocked` on purpose. `evaluate_stage` returns `already_done` as a positive blocker (`solver.py:602`), which is the right answer for admissibility — a finished stage must not be offered — but counting it as *blocked* made the census say the pipeline seizes up as it succeeds, with the blocked count climbing toward 72 precisely because the run was finishing. `blocked` now means only "the solver proved this cannot run". **The underlying issue is in `solver.py`, which this tool does not own**: the correction is applied in the replay tool's classification (`verdict_is_complete`), keyed on `already_done` being the sole reason, so a genuinely blocked stage cannot be laundered into this bucket.

### Deferral causes, split by whether contract population can fix them

| Bucket | Unknowns | Meaning |
|---|---|---|
| `coverage` | 5012 | the contract does not yet declare enough; §4.3 population removes these |
| `structural` | 3132 | gate state that is not on disk, glob inputs, config-optional gates — population never removes these |

Structural share of all stage verdicts: **26.0%**. 2971 deferred verdicts belong to a contract group that is not yet conformance-strict.

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
| `exec_5410_d19c15b58ab4_20260` | 2026-09-06T14:57:39Z | 1 | 27 | 15 | 29 |

## Divergences — the classes, never merged

| Class | Meaning | Count |
|---|---|---|
| `agree` | solver would have dispatched the same stage | 382 |
| `defer` | solver declines to have an opinion (hollow contract, indeterminate gate) | 977 |
| `already_done` | the dispatched stage was **already complete** — not a disagreement about control flow at all | 600 |
| **`skip`** | solver proves the dispatched stage was not runnable *for some other reason* — it would have refused the dispatch. Agreement in spirit. | **525** |
| **`choice`** | solver would confidently have run a *different* stage — a real disagreement | **14** |

Agreement rate is 41.5% over the 921 points that produced an opinion about control flow (`agree` + `skip` + `choice`). `already_done` and `defer` are outside that denominator: neither is a statement about which stage should run next.

### Already-complete dispatches — held apart from `skip`

**600** dispatches re-ran a stage the solver could see was already finished. This is real driver behaviour worth reading, but it is not evidence about solver quality, so it is counted in neither the skip column nor the agreement rate. The `rerun` and `operator` sources are deliberate re-runs; a `conductor` or walk source is the thrash the campaign is chasing.

| Dispatch source | Count |
|---|---|
| `conductor` | 367 |
| `operator` | 189 |
| `rerun` | 44 |

This class is not inflatable by the reconstruction: a surviving `.stage_done` marker whose final mtime is at or before `T` did exist at `T`, so the mtime witness cannot invent a completion. Its failure mode is the opposite — a marker rewritten late reads as absent, which surfaces as a choice divergence instead.

### How the choice divergences resolve

The 14 choice divergences resolve as **14 reconstruction artifacts and 0 genuine**. Only the genuine residue reaches the D12 gate. Each row states the criterion and the witness it needs, and every attribution is computed per run from the corpus bytes — no divergence is excused by prose.

| Resolution | Count | Criterion | Witness |
|---|---|---|---|
| `mtime_only` | 13 | the preferred stage emits no `kind=stage` ledger row anywhere in its run, so its done-timeline rests on the surviving `.stage_done` marker's mtime — which records the *last* write, not the first | absence of any `kind=stage` row for that stage |
| `content_postdates_point` | 1 | an artifact that decided the preferred stage's runnability records a commit **after** this decision point, so the producer witness fed the solver a revision the live run could not have shown it | `_meta.committed_at` on that artifact, stamped at commit time by `artifact_lifecycle.fingerprint_artifact` |
| **`genuine`** | **0** | neither witness applies — the replay has sound evidence and the solver still disagreed | — |

The two limitations are the first and sixth entries of *What this replay cannot prove* below. Neither witness can be satisfied by an absent field: an artifact with no `_meta.committed_at` is no proof and leaves its divergence in the genuine residue, so the attribution can only ever be made on positive evidence.

Divergences excused by a future-content commit, with their proof:

- `exec_5188_d19c15b58ab4_20260903T035354Z` seq 207 (2026-09-03T04:34:13Z): driver ran `gap_framing_compose`, solver would have run `missing_framing` — `understanding/gap_evaluations.json` records `_meta.committed_at` 2026-09-03T16:07:16Z, 11h33m after this decision point

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

| Driver ran | Solver would have run | Count | Resolution | Regression |
|---|---|---|---|---|
| `boundary_topic_resplit` | `content_brief_reanchor` | 7 | mtime-only reconstruction | no |
| `missing_framing` | `content_brief_reanchor` | 4 | mtime-only reconstruction | no |
| `gap_framing_compose` | `content_brief_reanchor` | 1 | mtime-only reconstruction | no |
| `sound_design_palettes` | `content_brief_reanchor` | 1 | mtime-only reconstruction | no |
| `gap_framing_compose` | `missing_framing` | 1 | content post-dates the point | no |

**No genuine residue.** Every choice divergence carries one of the two reconstruction witnesses above. That is what clears the D12 condition, and it is a statement about the instrument as much as about the solver — see the caveat under *Verdict*.

#### Traced to root cause

These accounts are hand-maintained and deliberately do not change the verdict — an explanation must never be able to promote anything. Where an account below describes a divergence that no longer counts, the thing that stopped it counting is the machine-computed witness in the resolution table, never the prose.

- **`content_brief_reanchor`** — `content_brief_reanchor` executes as a substep and never emits a `kind=stage` ledger row, so the replay has no event evidence for it at all and falls back to its `.stage_done` marker mtime. In exec_11871 the session log shows the stage completing at 01:08:45Z while the surviving marker is stamped 02:02:56Z — written early, invalidated, rewritten late. Every decision point in between therefore sees a stage the walk had already retired, and the solver correctly calls it runnable from state that is wrong.
- **`missing_framing`** — **Resolved: the replay was shown content from 11h33m in the future.** Superseded twice. The A-01 research-thin latch first diagnosed here was real and is fixed (`b01d8436`); with it gone the refusal at exec_5188 seq 207 became `missing_framing batch_fill — LLM must score 34 segment(s)`, and that one is an artifact of the producer witness.

  The run's `.archived/20260903T155920Z` copy of `understanding/gap_evaluations.json` is the pre-repair revision committed at 04:42:31Z, and it decides the question. Its 234 evaluations partition into three append blocks whose `_meta.repairs` stamps land strictly inside their own block, matching the three `missing_framing` dispatches exactly: **0–78 committed 04:34:05Z, 79–156 committed 04:39:57Z, 157–233 committed 04:42:31Z**. Unscored batch-coverage fills appear at indices **146–156 only** — inside the *second* block. Run 1's block carries **zero** of them and every row untagged. So at the 04:34:13Z decision point the artifact was run 1's 79 scored evaluations, the batch_fill condition was **false**, and rebuilding the snapshot with that revision gives `stage_done=True` → `already_done` → the solver **agrees** with the driver's `gap_framing_compose`. Rebuilding it with the 04:39:57Z revision reproduces the divergence, which is precisely why the driver re-dispatched `missing_framing` at 04:40:06Z (seq 245, source `rerun`): run 2's sparse shard is what introduced the fills. `seg_032` shows the mechanism in one row — scored `severity=medium/missing_callback` in block 1, an unscored `ok_with_light_bridge` fill in block 2, scored again in block 3.

  One correction to the record, since the timing argument is the whole case: the 34 fills in the surviving file carry **no repair stamp at all**. They are `filled_by=missing_framing_batch_coverage / reason=llm_sparse_shard_output`, minted by the stage body on a sparse LLM shard. The `_meta.repairs` instants (16:07:16Z, five `default_value` patches; 16:35:33Z, 45 `fabricate_evaluation` rows) describe *different* rows, none of which the predicate flags. The ~11.5h gap is real but the witness for it is `_meta.committed_at` (16:07:16Z, stamped by `artifact_lifecycle.fingerprint_artifact` over the body actually in the file), not the repair log. That is the witness `content_postdates_point` measures, and it is what excuses this divergence — this prose does not.

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

## Known-adjacent, deliberately not implemented

Recorded so they are not rediscovered from scratch. None of these is a gate, and none is owned by this tool.

- The `_MASTERING_SCHEMA_STAGES` short-circuit still swallows the research-thin refusal for `mastering_shape_agenda` and `mastering_shape_candidates`. Wiring it through is **not** obviously safe: the rollup's about-to-bind branch cannot fire before the first Shape stage runs, so a naive fix risks minting a *fresh* latch of the same shape as the A-01 one that `b01d8436` just removed.
- "Stale record versus live state" looks like the general shape of this codebase's recurring completed-but-inadequate class, of which `research_dossier_shape_core_stale` is one instance. A single predicate might cover several of them, but that is a refactor rather than a fix, and it is unowned.
- The `content_postdates_point` witness this report relies on is only as good as `_meta.committed_at` coverage. Artifacts written without going through `artifact_lifecycle.fingerprint_artifact` carry no stamp, so a future-content divergence on one of those would land in the genuine residue and veto. That direction is the safe one, but it means the reconstruction-artifact count is a floor, not an exact figure.
