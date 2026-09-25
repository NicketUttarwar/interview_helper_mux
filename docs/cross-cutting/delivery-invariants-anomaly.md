# `delivery_invariants` — the batch-1 anomaly, explained

**Status: SOLVED. Not an artifact. Not a dynamic-access hazard.** The failure was a real hidden
dependency: an **in-module call chain** reached from `recovery_controller.py`. Three of the four
symbols are load-bearing; one is safe to delete.

This closes the former open item: the mechanism was not understood and needed
a dedicated investigation before further subtraction of `delivery_invariants`.

---

## 1. Verdict

| Symbol | Lines | Delete? | Why |
|---|---:|---|---|
| `seed_order_heal_action` | 14 | **NO** | Called by the surviving in-module `apply_seed_order_heal` (line 548), which `recovery_controller.playbook_seed_order_prereq` calls at line 978. |
| `live_producer_authority` | 38 | **NO** | Called by `seed_order_heal_action` (line 161). |
| `seed_order_consumer_for` | 24 | **NO** | Called by `seed_order_heal_action` (line 162) on the `restamp` branch. |
| `_active_listen_delight_remutate_stages` | 3 | **YES** | Zero references in `src/`, `tools/`, `scripts/`, `tests/`, or any non-Python file. A 3-line compat wrapper over `active_remutate_stages`. |

**Net: 3 lines are deletable, not 79.** H-12's projected 532 deletable lines in this module must be
re-derived; the "no external importer" figure is not the deletable figure.

---

## 2. The failing test and the exact failure

```
tests/test_i1_g0_flush_before_gate.py::test_i1_g0_systemexit_flushes_pending_queue
```

```
E  RuntimeError: seed order: complete audio_preclean before running transcript_review_build

src/interview_mux/homunculus/runtime.py:377: RuntimeError
```

The raise site is `homunculus/runtime.py:375-379`, the tail of `dispatch_stage`:

```python
blocked = _seed_prereq_block(ctx, stage)
if blocked:
    raise RuntimeError(
        f"seed order: complete {blocked} before running {stage}"
    )
```

---

## 3. The mechanism

### 3.1 The seed-order block is raised on **every** run of this test, pass or fail

This is the fact that makes the whole anomaly legible, and nobody had checked it.

The fixture writes `run_meta.json` with `homunculus_version: 0.1.0`, so
`has_dispatch_ledger(ctx)` is true and `pipeline.run_single_stage` takes the
`dispatch_stage` branch (`pipeline.py:617`) rather than `run_wrapped_stage`. Inside
`dispatch_stage`, `_seed_prereq_block(ctx, "transcript_review_build")` walks
`ANALYSIS_ORDER` and finds `audio_preclean` — `ANALYSIS_ORDER[0]`, not done, and not
exempted, because `llm_flow_hardening._seed_order_skip_stage` only waives `audio_preclean`
on a *partially accelerated* run. So the `RuntimeError` fires unconditionally.

The test is green in the original tree **only because the failure is then healed**:

```
pipeline.run_single_stage("transcript_review_build")
  └─ dispatch_stage → RuntimeError("seed order: complete audio_preclean before …")
     └─ pipeline.py:631  except Exception as exc
        └─ recovery_controller.handle_stage_failure(ctx, stage, exc)
           └─ error_class "seed_order_prereq"  (recovery_controller.py:1605)
              └─ playbook_seed_order_prereq(ctx, exc)            :908
                 └─ delivery_invariants.apply_seed_order_heal    :978   ← survives the cut
                    └─ seed_order_heal_action                    ← DELETED
                       ├─ live_producer_authority                ← DELETED
                       └─ seed_order_consumer_for  (restamp branch only)  ← DELETED
        └─ recovered=True, resume="audio_preclean"
           └─ pipeline.py:675  run_wrapped_stage(ctx, stage, _impl)   ← bypasses dispatch_stage,
                                                                        so seed order is not
                                                                        re-checked
              └─ stage writes queue+clips, G0 gate raises
                 SystemExit("Transcript review required")             ← what the test asserts
```

`apply_seed_order_heal` was **not** in the delete set — it has an external caller. Its call to
`seed_order_heal_action` is on an unguarded line (`delivery_invariants.py:548`), so with the callee
gone it raises (`NotImplementedError` from the shim, or `NameError` without one). That exception is
swallowed by the blanket handler wrapping the whole playbook dispatch —
`recovery_controller.py:1469-1770`, `except Exception: recovered = False` — so the heal silently
becomes a no-op, no retry happens, and the original seed-order `RuntimeError` propagates to the
assertion.

**This is exactly the "guard silently stops guarding" shape §1.4.4 warned about**, one level
removed: the swallowed exception is silent, but its consequence (an unhealed seed-order block) is
loud. Had the pin been on a *restamp*-eligible producer instead of `audio_preclean`, only
`seed_order_consumer_for` would have been missing and nothing would have failed at all.

### 3.2 Why static search said "unreferenced"

It said "unreferenced **outside the defining module**", which is a different claim. All three are
referenced *inside* `delivery_invariants.py`:

```
apply_seed_order_heal  →  seed_order_heal_action  →  live_producer_authority
                                                 →  seed_order_consumer_for
```

This is the third recurrence of the same defect class previously recorded during guardrail subtraction
(§1.4.1 `AcceptanceResult`, §1.4.3 the 49-function Batch 1 revert). The fix already exists:
`tools/subtraction_predict.py::_closure_evict`.

### 3.3 Why restoring one symbol at a time never helped

Two independent reasons, either of which alone defeats single-restore bisection:

1. **There are two live dependencies, not one.** The chain is two links deep and forks. Restoring
   `seed_order_heal_action` alone leaves `live_producer_authority` missing; restoring
   `live_producer_authority` alone leaves `seed_order_heal_action` missing. Every single-symbol
   probe fails, which reads as "no individual symbol is responsible" — the opposite of the truth.
   Restoring **two** (`seed_order_heal_action` + `live_producer_authority`) passes.
2. **The raising shim shadowed the restore base.** Batch 1 appended
   `def seed_order_heal_action(...): raise NotImplementedError(...)` to the end of the file
   (§1.4.5 shim ruling). Because Python's last definition wins, that append **by itself** breaks the
   test with **nothing deleted at all** — verified below. Any restore performed against a base that
   still carries the shim inherits the break unless the restored definition is appended after it.

Combined, single-restore bisection over this module could not have produced a green run. "Only the
full restore fixed it" was a property of the *probe*, not of the code.

---

## 4. Evidence

Reproduced on the working-tree module, which is byte-identical to its `pre-subtraction-snapshot-w1`
blob (`sha256 6f4d03f2…621f`, verified before and after every variant). Node under test is the one
in §2; each row is a fresh `pytest` process.

| Variant of `delivery_invariants.py` | i1 node |
|---|---|
| original (control) | **PASS** |
| four symbols deleted + batch-1 raising shim | FAIL |
| four symbols deleted, no shim | FAIL |
| original **+ raising shim appended, nothing deleted** | **FAIL** |
| restore `seed_order_heal_action` only | FAIL |
| restore `live_producer_authority` only | FAIL |
| restore `seed_order_consumer_for` only | FAIL |
| restore `_active_listen_delight_remutate_stages` only | FAIL |
| restore `seed_order_heal_action` + `live_producer_authority` | **PASS** |
| restore `seed_order_heal_action` + `seed_order_consumer_for` | FAIL |
| restore all three chain members | **PASS** |
| delete `seed_order_heal_action` only | FAIL |
| delete `live_producer_authority` only | FAIL |
| delete `seed_order_consumer_for` only | PASS (not covered by this test — see below) |
| delete `_active_listen_delight_remutate_stages` only | **PASS** |
| delete the four **plus** `apply_seed_order_heal` | FAIL (`recovery_controller:978` then has no callee) |

`seed_order_consumer_for` is only reached on the `restamp` branch, which this test does not take
(`audio_preclean` has no live-producer authority → `unmark`). Deleting it alone is caught elsewhere —
three new failures on the restamp path:

```
tests/test_ende_heal_stamp_pin.py::test_ende_integral_master_may_restamp
tests/test_major_thrash_hardening.py::test_seed_order_music_epoch_restamp
tests/test_major_thrash_hardening.py::test_seed_order_restamp_live_sdp
```

The one safe deletion was confirmed against every test file naming `delivery_invariants`, plus
`test_i1_g0_flush_before_gate`, `test_recovery_controller`, `test_heal_routing`,
`test_delivery_guardrails` (200 tests): failing node-id set **identical** to baseline, 0 new,
0 fixed.

### 4.1 Hypotheses ruled out

- **Test-state pollution / order dependence — ruled out.** The failure is deterministic in a
  single-test process, and the control passes in a single-test process. Run in suite order
  (`pytest tests/test_i*.py`, 184 tests, alphabetical, no randomising plugin installed) the original
  yields 2 pre-existing failures and the deletion yields exactly those 2 plus the i1 node — a clean
  one-node delta in both isolation and suite order. The test's `isolated_run_ctx` repoints `run_dir`
  to a per-test `tmp_path`, so it shares no state with siblings.
- **Import-time side effects — ruled out.** The module registers nothing at import: no decorators,
  no registry, no dispatch table, no mutable module-level structure beyond four string constants and
  one tuple of relative paths.
- **Dynamic access (`getattr` / `globals()` / `__all__` / `importlib` / `inspect.getmembers`) —
  ruled out**, here and repo-wide. See §5.
- **Byte-level difference in the "full restore" — ruled out.** The full restore was genuinely
  byte-identical; the *partial* restores were the misleading probes (§3.3).

---

## 5. Does this generalise? Yes — but not in the direction that was feared

### 5.1 There is no dynamic-access hazard class in this repo

An AST scan of every file under `src/interview_mux` finds:

- **zero** `getattr` calls with a computed (non-string-literal) name that resolve a module symbol.
  The only four computed `getattr` calls are instance-attribute reads on `ctx` using private
  module constants (`artifact_lifecycle.py:602/627/660`, `reentry.py:70`);
- **zero** uses of `globals()`, `vars()`, `eval`, `exec`, `dir()`, `inspect.getmembers`, or
  `importlib` for symbol resolution.

String-keyed dispatch tables *do* exist (`heal_routing.PLAYBOOK_REGISTRY`,
`recovery_controller`'s error-class chain), but they are keyed on **error-class strings**, not
symbol names, and `subtraction_predict.py` already tokenises string constants
(`_referenced_names`) and scans YAML/JSON/shell (`scan_references(strict=True)`).

**So "statically-unreferenced symbols that are load-bearing via dynamic access" is not a class of
hazard here.** That lead can be retired.

### 5.2 The class that *is* real: in-module and inter-candidate call chains

Same shape as this anomaly, and large. Today's
`python tools/subtraction_predict.py plan` reports:

```
closure pass evicted 210 symbols (4365 lines) with surviving callers
```

Those 4,365 lines are symbols that a per-symbol "no external importer" view calls deletable and that
are in fact pinned. This module's three are among them. **The tool already handles this** — see
`_closure_evict` — and verifiably so: run today,

```
python tools/subtraction_predict.py plan --modules delivery_invariants --verbose
…
EXTERNAL:  15 symbols, 389 lines
  delivery_invariants.live_producer_authority       38L  self-contained   ← evicted from DELETABLE
  delivery_invariants.seed_order_consumer_for       24L  self-contained   ← evicted
  delivery_invariants.seed_order_heal_action        14L  self-contained   ← evicted
DELETABLE: 1 symbols, 3 lines
  delivery_invariants._active_listen_delight_remutate_stages  3L
```

gives exactly the verdict this investigation arrived at empirically. **The anomaly is residue from
the pre-`_closure_evict` planner**, not a live gap. No change to the campaign's *scanning* is needed.

A repo-wide strict `orphans` run over *all* candidate modules agrees, and is the stronger statement —
across the whole campaign only two symbols are unreferenced anywhere, one of them the 3-line wrapper
cleared in §1:

```
ORPHANS (no reference anywhere) — 2 symbols, 65 lines
  artifact_completeness.build_gap_fill_context                     62L  FunctionDef
  delivery_invariants._active_listen_delight_remutate_stages        3L  FunctionDef
```

The other three do not appear because strict mode counts intra-module references — exactly the
signal the per-symbol view discarded. (`build_gap_fill_context` is the W0.1 cascade tail already
logged during W0.1 of guardrail subtraction.)

### 5.3 What must change: two methodology rules

These are the transferable findings from that investigation.

1. **Single-symbol restore is an invalid bisection method.** A delete set that contains a call chain
   cannot be bisected one symbol at a time: every single-restore probe fails, and the operator
   concludes the coupling is unattributable. Bisect **cumulatively** (restore 1, then 1+2, then
   1+2+3) or by halves, always against a base with **no shims**. Had batch 1 done this, the answer
   would have taken one run.
2. **A raising shim appended to a module can shadow a live definition.** `cat >> module.py` with a
   `def X(): raise NotImplementedError` overrides any surviving `X`, because the last definition
   wins. §4 shows the shim alone breaking the test with nothing deleted. Every shim append must be
   followed by a check that the name it defines is genuinely absent from the rest of the file:

   ```bash
   .venv/bin/python - <<'PY'
   import ast; t=ast.parse(open("src/interview_mux/<mod>.py").read())
   names=[n.name for n in t.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
   dupes=[n for n in set(names) if names.count(n)>1]
   assert not dupes, f"shim shadows a live definition: {dupes}"
   PY
   ```

---

## 6. Consequences for H-12 and the campaign

- **Unblock, with a corrected set.** Delete `_active_listen_delight_remutate_stages` (3L) only.
  Zero new failures, evidence in §4.
- **H-12's line budget is wrong.** "532L deletable" derives from the per-symbol view. The
  closure-correct figure for this module is 3 lines without caller rewrites. Re-derive every §2
  and §9 line count from `plan` output, not from importer counts — §1.4.3 already said the
  no-rewrite set is an order of magnitude smaller than projected, and this module is a clean
  instance of that.
- **The seed-order heal is live, not dead policy.** The batch-1 shim comment asserted the solver
  makes `seed order: complete X before Y` "unreachable by construction (plan §2.3)". It is reached
  today, on the 0.1.0 brain, in the *first stage a run dispatches* — `dispatch_stage` raises it and
  `playbook_seed_order_prereq` heals it. H-02's "solver admissibility makes seed order unreachable
  by construction" claim should be marked **not yet true** until `dispatch_stage` stops raising it.
- **No new hole.** Nothing was shipped, so there is no unguarded failure mode to patch. The correct
  §6.05 outcome for `delivery_invariants` is "3 of 4 were load-bearing; the tool now says so".
