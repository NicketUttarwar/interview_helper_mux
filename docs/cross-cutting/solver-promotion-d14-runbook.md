# Solver promotion — D14 live-confirmation runbook

Brain **0.2.0**'s deterministic solver (`src/interview_mux/solver.py`) is built, tested and
**armed but not enabled**: `MUX_SOLVER_AUTHORITATIVE` defaults **False**. Three gates pass —
door/lease safety (`84b79344`), trajectory (`d2fbc02d`, `tests/test_solver_trajectory.py`) and
D12 replay (`1892ec5e`). The default was deliberately **not** flipped, because D12 passes by
*attribution*, not proof: all 14 choice divergences are excused as limits of the replay
instrument (13 `mtime_only`, 1 `content_postdates_point`), so the solver was never independently
shown right at those points. See
[solver-replay-validation.md](solver-replay-validation.md).

**D14 is the missing evidence:** one live full-auto walked by the solver itself. This document
is how to run it cold, weeks later, with no memory of the night it was written.

---

## Verdict on the prerequisite: the run will NOT stall at the gates

The audit finding is correct as stated — `_gate_verdict` (`solver.py:510`) reads **no**
`gate_decisions.json`, and `set_gate_decision` is reachable only from the LLM tool loop
(`homunculus/loop.py:238`), which brain 0.2.0 never runs. **It does not matter for D14.** Gate
resolution under full-auto never needed a persisted decision, on two independent counts.

**1. The solver's gate term cannot block in full-auto.** Traced:

- `evaluate_stage` step 3 → `_gate_verdict(ctx, sid, posture)` (`solver.py:510-542`).
- For each gate from `gates_blocking(stage)`, `gate_open()` (`solver.py:426`) asks the *live
  pipeline predicates* — `gates.check_transcript_review_pending`,
  `gap_vo_gates.check_gap_framing_decision_pending`, `gates.check_g1_vo`,
  `gates.check_g_publish_pending`. None of them reads `gate_decisions.json`.
- `gate_enforcement(gate, FULL_AUTO)` (`solver.py:486-507`) returns `auto_accept` for **G0,
  G-Framing, G1 and G-Publish**.
- An `auto_accept` open gate is appended to **`unknowns`** as `gate_auto_accept_pending:<gate>`,
  never to `reasons`. `StageVerdict.admissible` is `not reasons`, so the stage stays
  **admissible-but-deferred**: it loses `confident`, and `authoritative_sequence` rule 2 hands it
  back to seed order (`solver.py:1234-1236`).
- Posture itself resolves correctly on a real driver run: `posture_for` reads `run_meta.json`
  via `automation_run.is_full_auto_run`, and `tools/full_auto_driver.py:13841` writes
  `run_mode: full-auto` + `full_auto: true`.

Pinned by `tests/test_solver_posture.py::test_open_g0_blocks_analysis_unless_full_auto` and
`::test_g0_enforcement_follows_the_posture`.

**2. Gate *satisfaction* is not the solver's job in any posture.** G0 is signed off by the
driver (`tools/full_auto_driver.py:complete_g0` → the GUI complete API); G-Framing auto-accepts
through `gap_vo_gates.maybe_auto_accept_gap_gate_defaults`, called from `pipeline.py:264` and
`:422`, which is enabled on 0.1.0/0.2.0 via `has_homunculus_features` +
`recommended_framing_action == auto_resolve`. Both are entirely unaffected by
`MUX_SOLVER_AUTHORITATIVE`. The walk also truncates its own candidate list at
`transcript_review_build` while G0 is open (`homunculus/agenda.py:_truncate_analysis_while_g0_open`),
so post-G0 stages are never even offered to the solver until the driver closes G0.

**Persisting gate decisions is therefore a telemetry/coverage item (plan D10), not a blocker for
D14.** Its cost is that gate unknowns keep the verdict non-`confident`, which lowers the share of
the walk the solver can *justify* — see the risks section.

### The two narrow gate risks that are real

- **Preclean is the one gate that blocks in every posture.** `gate_enforcement` returns `block`
  for `source_preclean` unconditionally (`solver.py:497`), and `_preclean_auto_enabled`
  (`solver.py:452`) is true when `run_meta.audio_preclean.enabled` is set with no `decisions`
  and no `requested_at`. If that shape ever appears, `audio_preclean` carries a permanent
  positive blocker `gate_open:source_preclean` and is retired for the run. Scope is one stage,
  not the walk; Preclean is never auto-run by design ([operator-gates.md](../workflows/operator-gates.md)).
  Watch for that exact reason string in the halt panel.
- **`transcript_review` is not a pipeline stage.** If it ever reaches the candidate list with G0
  closed, `evaluate_stage` returns `not_a_pipeline_stage` (a positive blocker), so instead of the
  walk's `g0_pending` warning line you would see a solver **structural halt** whose reason family
  is `not_a_pipeline_stage`. Same outcome, different log; do not read it as a broken run.

---

## Stated facts that did not check out

Flagging these because the runbook is only useful if its numbers are real.

- **"All three enforcing groups (`prepare`, `understand-c`, `sound`)" is stale.**
  `contract_conformance.STRICT_GROUPS` is now **six**: `prepare`, `understand-a`,
  `understand-b`, `understand-c`, `plan_rank`, `sound` (commit `4e4ef5a0`). The recorded run
  therefore bites on six groups, not three — more value, and more blast radius.
- **"~2,033 stage evaluations and ~6.3 s per 72-stage walk" is not recorded anywhere in the
  tree.** The only measured figure is `tests/test_solver_trajectory.py`: *"One full 72-stage
  drain costs ~2.6k stage evaluations and ~15 s"*, measured on `exec_11871`, the richest real
  run. Treat ~2.6k/~15 s as the number to plan against; the floor framing still holds.
- **`st_birthtime` appears nowhere in the repo**, including
  [test-isolation.md](test-isolation.md). The birthtime-not-mtime sweep rule below is operator
  practice, not codified policy.
- **`ASSETS/executions` holds 35 `exec_*` directories plus `.execution_counter`** = the 36
  entries you were told to preserve. test-isolation.md says "35 genuine executions"; both are
  right, they just count differently.

---

## 1. Exact invocation

Two variables, both read from the process environment:

- `MUX_SOLVER_AUTHORITATIVE=1` → `solver.solver_authoritative()` (`solver.py:126`), read
  uncached on every call. This is the only flag that lets the solver choose.
- `MUX_CONTRACT_RECORD=1` → `contract_conformance.recording_enabled()`, **cached per process**
  (`_record_flag`). It arms `write_staging.resolve_read_path` / `resolve_write_path` to record
  touches, and `write_staging.run_wrapped_stage` flushes them to
  `operator/contract_observed.json` after every stage via `warn_on_mismatch` → `flush_observed`.
  No such file exists anywhere in the tree today, so runtime conformance currently **skips** and
  all six strict groups rest on static evidence alone. One run validates the solver *and* the
  ratchet.

Leave `MUX_SOLVER_SHADOW` alone — it defaults ON, and it is what writes
`operator/solver_decision.jsonl` under authority (`solver.py:1249`). With it off you get an
authoritative run with no telemetry.

```bash
cd /Users/nicketuttarwar/IDEProjects/interview_helper_mux

# Stop any prior stack FIRST — a server already running does not have the new env.
python tools/full_auto_daemon_launch.py stop
pgrep -fl 'full_auto_driver\.py|interview_mux' || echo 'clean'

MUX_SOLVER_AUTHORITATIVE=1 \
MUX_CONTRACT_RECORD=1 \
MUX_RUN_MODE=full-auto \
MUX_HOMUNCULUS_VERSION=0.2.0 \
MUX_FRESH=1 \
MUX_FORENSICS=1 \
MUX_KEEPALIVE=1 \
MUX_INPUT_AUDIO=ASSETS/input/<INPUT_FILE> \
./scripts/run.sh --full-auto --input ASSETS/input/<INPUT_FILE>
```

- **Restarting the stack is mandatory, not hygiene.** `tools/full_auto_daemon_launch.py:_popen`
  copies `os.environ` into both the detached server and the driver, but only at spawn time, and
  `ensure_server` skips the spawn when a healthy server already answers. The walk
  (`homunculus/agenda.py:walk_seed_agenda` → `_walk_sequence`) runs inside the **server's** job
  thread, so a stale server silently gives you a non-authoritative run.
- **Set `MUX_HOMUNCULUS_VERSION=0.2.0` explicitly.** The daemon injects `0.1.0` when the
  variable is absent (`full_auto_daemon_launch.py:236`, `:263`), regardless of
  `version.default_version()`. Authority demotes the conductor on any brain
  (`homunculus/runtime.py:conductor_owns_control_flow` returns False under authority), but you
  want the deterministic brain named on the tape.
- Confirm the flag actually landed before you walk away:

```bash
RUN=$(cat ASSETS/full_auto_current_run.txt)
curl -s "http://127.0.0.1:8765/api/runs/$RUN/solver-decision" | python -m json.tool | head -20
# expect: "authoritative": true, "shadow_logging": true
```

## 2. Fresh-run requirement

Non-negotiable, per [AGENTS.md](../../AGENTS.md) and
`.cursor/plans/full_auto_forensics_run.plan.md` §0.1/§1.1:

- Kickoff is **always** `MUX_FRESH=1` → a brand-new `exec_*`. `scripts/run.sh` already defaults
  `MUX_FRESH` to `1` for full-auto launches; set it anyway so the intent is on the record.
- Never bind `MUX_RUN_ID` to an old campaign directory, and never copy `master/`,
  `understanding/` or `.stage_done` from a prior execution.
- `exec_11871_d19c15b58ab4_20260916T002245Z` is a read-only forensic artifact (it is the pinned
  replay and trajectory corpus). Do not resume it, prune it, or let a sweep touch it.
- On a bug mid-run: diagnose → cascade pytest with `MUX_FORENSICS=0` → patch the producer →
  **continue the same `run_id`** with `MUX_FRESH=0`. Do **not** spawn a second fresh exec to
  verify a late-stage fix.

## 3. What to watch, live

```bash
RUN=$(cat ASSETS/full_auto_current_run.txt)
BASE="ASSETS/executions/$RUN"

tail -f ASSETS/full_auto_console.log &
tail -5 "$BASE/operator/solver_decision.jsonl"
python -m json.tool < "$BASE/operator/defect_ledger.json"      | head -40
python -m json.tool < "$BASE/operator/ship_reachability.json"  | head -40
python -m json.tool < "$BASE/operator/invalidation_epoch.json"
ls "$BASE/operator/contract_observed.json" && echo 'recorder is writing'
ls "$BASE/.stage_done" | wc -l
```

- **`operator/solver_decision.jsonl`** — one row per pick plus halt/pause rows. Capped at 400
  rows (`MAX_DECISION_ROWS`), newest last. Fields that matter: `would_choose`,
  `would_choose_confident`, `deferred`, `halted`, `halt_kind`, `excluded[].reason`.
- **GUI solver halt panel** — `SolverHaltPanel.tsx`, rendered inside `PhaseWorkbench.tsx`,
  backed by `GET /api/runs/{run_id}/solver-decision` (`web/server.py:1067`). It shows a live
  evaluation, not just the log, and separates *blocked* from *deferred* from *paused*. Its
  footer flips from "shadow-only, decides nothing" to **"authoritative"** — a free confirmation
  that the flag took.
- **`operator/defect_ledger.json`** (`defect_ledger.DEFECT_LEDGER_REL`) — advance-past rows. A
  door refusal must still produce one under authority; a missing row is a D14 failure.
- **`operator/ship_reachability.json`** (`ship_reachability.REACHABILITY_REL`) — the severance
  verdict. Note the **halt** is opt-in: `ship_reachability.halt_enabled()` requires
  `MUX_SHIP_REACHABILITY_HALT=1`, so by default a proven severance is recorded and the walk
  continues. Leave it off for D14; read the file instead.
- **`operator/invalidation_epoch.json`** (`master_epoch.EPOCH_REL`) — epoch bumps. Rapid churn
  here alongside repeated solver picks of the same stage is the thrash signature.
- **`operator/contract_observed.json`** — should appear within the first few stages. If it never
  appears, `MUX_CONTRACT_RECORD` did not reach the server process and the ratchet half of the
  run is void.

## 4. Lease pause vs structural halt

Both empty the admissible set; they need opposite responses, and conflating them has already
sent an operator hunting a blocker that never existed.

- **`lease_pause`** — the GUI holds a fresh lease (`lease_permits_acting` mirrors
  `automation_run.gui_holds_fresh_lease` read-only). Another session is driving. Nothing is
  broken, no producer to chase; it clears itself. Log line: *"paused — the GUI holds a fresh
  lease…"*, reason code `lease_held_by_gui`, and the pause is decided **before** any per-stage
  evaluation (`solver.py:1214`).
- **`structural_halt`** — nothing is runnable until on-disk state changes. Log line: *"structural
  halt — admissible set is empty…"* with a `reason_families` histogram in the line itself.

**The field name is inconsistent, and that inconsistency is unfixed.** Grep for both:

- `Decision.as_row()` writes it as **`halt_kind`** → this is what lands in
  `operator/solver_decision.jsonl`.
- `halt_payload()` writes the same value as **`kind`** → this is what the API/GUI payload and
  the log `detail` carry.

```bash
# from the persisted log
python - <<'PY'
import json, pathlib
run = pathlib.Path("ASSETS/full_auto_current_run.txt").read_text().strip()
log = pathlib.Path("ASSETS/executions") / run / "operator/solver_decision.jsonl"
for line in log.read_text().splitlines():
    row = json.loads(line)
    if row.get("halt_kind"):
        print(row.get("at"), row["halt_kind"], row.get("would_choose"))
PY

# from the API payload (same value, different key)
curl -s "http://127.0.0.1:8765/api/runs/$RUN/solver-decision" \
  | python -c 'import json,sys; h=json.load(sys.stdin)["halt"]; print(h["kind"], h["reason_code"], h["blocked_total"])'
```

## 5. Pass / fail criteria

**D14 confirmed when all of these hold:**

- The run reaches a committed `master/master.wav` and passes the normal ship bar
  (verify_master + listen-delight + PMQ), with no quality waivers.
- `operator/solver_decision.jsonl` contains **no** `structural_halt` row that a later human
  reading judges premature — i.e. every halt is a state fact, not a contract lie.
- Every stage the run needed actually ran. No stage silently retired.
- Every door refusal has a matching `refuse_dispatch` row in `operator/defect_ledger.json`.
- `operator/contract_observed.json` exists and covers the strict groups, and
  `pytest tests/test_contract_conformance.py` is green against it afterwards.

**D14 falsified by any one of these:**

- **A premature halt.** The sequence ends while work remained; `halt_kind` is `structural_halt`
  with `lease_ok: true`.
- **A stage retired by an over-declared `inputs.hard`.** This is the specific failure promotion
  introduces, and the halt line is built to expose it: a `hard_input_*` family logged against a
  stage whose declared `producer` already ran. Read `halt_payload().hard_input_blockers` — each
  entry carries the artifact, its declared producer and `declared_hard_inputs`, which is what
  separates a wrong declaration from a genuinely missing input. Fix the **contract**, not the
  solver.
- **A missing defect row.** A stage the door refused, with no `refuse_dispatch` row — that means
  the solver swallowed the refusal instead of handing the stage to the walk, and
  `ShipUnreachable` became unreachable. This is exactly what `84b79344` fixed; a recurrence is a
  regression.
- **A wrong master.** Right length, wrong content — inverted producer/consumer order, a stage
  run against stale inputs, zero-ms keeps. Cross-check against
  [publishability-contract.md](publishability-contract.md).

## 6. Abort and rollback

Stopping mid-run:

```bash
python tools/full_auto_daemon_launch.py stop      # driver + keepalive + detached server
# never a broad pkill
```

Reverting to previous behaviour — the flag is the whole rollback:

```bash
unset MUX_SOLVER_AUTHORITATIVE     # then restart the stack so the server re-reads env
```

With it unset, `_walk_sequence` returns `iter(walk_stages)` and the walk is byte-for-byte what
it was (`tests/test_solver_inert.py` pins this). Brains **0.0.0** (original linear walk) and
**0.1.0** (LLM conductor) both remain selectable from the Start-tab slider —
`homunculus/version.py` registers all three, and the GUI list is dynamic, so no rebuild is
needed. A resumed run keeps the `homunculus_version` already recorded in its `run_meta.json`.

Conformance rollback, independent of the solver:

```bash
MUX_CONTRACT_STRICT_GROUPS=prepare   # narrow enforcement to one group
MUX_CONTRACT_STRICT_GROUPS=          # empty string ⇒ enforcement disabled
# unset                              ⇒ fall back to the STRICT_GROUPS constant (six groups)
```

`contract_conformance.strict_groups()` honours the variable whenever it is *set*, including
empty. Recording itself (`MUX_CONTRACT_RECORD`) is separate and never gates a stage: runtime
conformance only ever warns.

## 7. Known risks to watch

- **This run is carrying more weight than a clean gate pass would imply.** D12 passed on
  attribution: 14 of 14 choice divergences excused as replay-instrument limits. The solver was
  not independently shown right at any of them. If the live run surfaces a genuine
  disagreement, the honest reading is that the replay could not see it — not that the run is
  unlucky.
- **Perf.** Every pick costs a full sweep of the remaining candidates, so the walk is
  quadratic-ish in stage count. Measured floor: **~2.6k stage evaluations, ~15 s** of pure
  decision time per 72-stage drain (`tests/test_solver_trajectory.py`, on `exec_11871`). That is
  a **floor** — it grows as contracts populate, because a satisfied hard input costs a
  `committed()` check plus a sufficiency lookup that an absent one short-circuits.
- **The trajectory properties are sharp on permanent retirement, blunt on mere deferral.** They
  catch a stage the solver never admits at all; a stage it merely keeps postponing while
  yielding others can still slip through.
- **The reconstruction-artifact count is a floor.** The `content_postdates_point` witness needs
  `_meta.committed_at`, which only `artifact_lifecycle.fingerprint_artifact` stamps. Artifacts
  written outside it carry no stamp, so a future-content divergence on one of those lands in the
  genuine residue.
- **Gate decisions are not persisted** (Part 1's subject). Consequence for this run: gate
  unknowns keep verdicts non-`confident`, so the solver's *justified* share stays low and much
  of the walk runs as `deferred_to_walk` seed order. A D14 pass under those conditions proves
  the solver is **safe**, not that it is **in charge**. Plan D10 owns closing that.
- **Coverage context, so the log reads sanely:** 37 of 72 stages declare a concrete hard input,
  35 declare none. On an empty run the census is exactly `0 confident / 35 deferred / 37
  blocked` — a tautology, not a signal. Live shadow on a fresh run measured 2 of 72 confidently
  admissible.

## 8. Post-run checklist

```bash
RUN=$(cat ASSETS/full_auto_current_run.txt)
BASE="ASSETS/executions/$RUN"

# 1. the ship bar
ls -l "$BASE/master/master.wav"
python -m json.tool < "$BASE/operator/execution_report.json" | head -40

# 2. the two artifacts this run existed to produce
tail -20 "$BASE/operator/solver_decision.jsonl"
python -m json.tool < "$BASE/operator/contract_observed.json" | head -40

# 3. the ratchet now has runtime evidence — run it
pytest tests/test_contract_conformance.py tests/test_solver_posture.py \
       tests/test_solver_authoritative.py tests/test_solver_inert.py

# 4. counter advanced sanely (was 13147 when this doc was written)
cat ASSETS/executions/.execution_counter

# 5. inventory: 35 exec_* + .execution_counter == 36 entries before this run
ls -d ASSETS/executions/exec_* | wc -l
ls -A ASSETS/executions | wc -l
```

**Sweeping test-fixture execution directories — classify by birthtime, never mtime.**

An mtime filter nearly destroyed two genuine runs. mtime moves whenever anything inside a run
directory is rewritten, including a late marker or an archived artifact, so a real run from
hours ago can look newer than the fixture noise around it. Birthtime does not move.

```bash
# macOS: %SB is st_birthtime. Inspect before deleting anything.
for d in ASSETS/executions/exec_*; do
  stat -f '%SB  %N' -t '%Y-%m-%dT%H:%M:%SZ' "$d"
done | sort

# A fixture leak is small and has no ledger; a genuine run has both.
for d in ASSETS/executions/exec_*; do
  printf '%s  ledger=%s  size=%s\n' "$d" \
    "$(test -f "$d/mastering/homunculus/ledger.json" && echo yes || echo no)" \
    "$(du -sh "$d" | cut -f1)"
done
```

Also sweep `MagicMock/mock.run_dir/*` at the repo root — those are pytest leaks from mocked
`RunContext` objects, not executions. The autouse redirect in `tests/conftest.py` is what keeps
the suite off the real tree; if fresh `exec_*` directories appear from a pytest session rather
than from this run, that is a broken isolation fixture and belongs in
[test-isolation.md](test-isolation.md), not in a delete loop.

Never `git stash` / `reset` / `checkout` to clean up: the working tree carries thousands of
uncommitted `rstm-results/` and `MagicMock/` paths that must survive.

---

## See also

- [solver-replay-validation.md](solver-replay-validation.md) — the D12 verdict, its attributions
  and its stated limits. Read the verdict box before quoting the gate.
- [test-isolation.md](test-isolation.md) — what keeps the suite off the live executions tree.
- [stage-contracts/00-INDEX.md](stage-contracts/00-INDEX.md) — per-stage contracts; the file to
  edit when a `hard_input_*` halt turns out to be an over-declaration.
- [mastering-homunculus.md](mastering-homunculus.md) — brain registry and the Start-tab slider.
- [artifact-ownership.md](artifact-ownership.md) — `operator/solver_decision.jsonl` and
  `operator/contract_observed.json` each hold an `ops` ALLOW row; the writers go quiet rather
  than write illegally if that ever tightens.
- [operator-gates.md](../workflows/operator-gates.md) — G0, G-Framing, G1, Preclean, G-Publish
  in full.
