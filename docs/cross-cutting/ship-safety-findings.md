# Ship-safety findings — follow-on work

Record of defects in the **ship-safety net**, all discovered while implementing
[.cursor/plans/solver_brain_020.plan.md](../../.cursor/plans/solver_brain_020.plan.md) and **none of them part of that plan**.
The operator ruled that the solver plan closes at its **written bar**; these are tracked here as separate follow-on work.

Five discrete defects (findings 1, 2, 3, 5, 6) plus one structural gap (finding 4).

**Fix order is `2 → 4 → 1`.** Finding 1 is **not** closed by the reachability fix; it is closed by Finding 4's
defect-on-bad-output remedy, which is only trustworthy once Finding 2's fail-open is closed. See
[§ Why the reachability fix does not close Finding 1](#why-the-reachability-fix-does-not-close-finding-1).

---

## Headline evidence — the asymmetry is measured, not theoretical

**`exec_5570` passed PMQ with `publish_allowed: True` and ZERO failed checks, while seven stages were stamped done with
outputs that are absent or schema-invalid.**

- Absent: `selection_framing_apply`, `sound_design_vo_finalize`, `junction_snip_qa`.
- Schema-invalid: `mastering/research/rollup.json` — missing `field_reports` and `salience_map`.
- Corroborated independently: `./scripts/verify_artifact_contract.sh` flags the same artifacts.

A run shipped clean while its own outputs were missing.

**Rate across the 30 most recent real full-auto runs:** **79 findings on 1,156 checked artifacts (6.8%)**, firing in
**16 of 30 runs**, ~5 per run. The three most recent completed runs (`exec_11871`, `exec_11676`, `exec_11630`) fire
**zero**, so this is not a blanket false positive. Of the 79: **46 `partial`** (present but invalid — unambiguous) and
**33 `pending`** (declared output absent — triage first, since a conditionally no-op stage may legitimately produce
nothing).

---

## Finding 1 — reachability is blind to the selection chain (LIVE WRONG-MASTER PATH)

**Status: PARTLY CLOSED.** The blindness itself is **fixed** — the selection chain **IS** on `critical_path()` as of the
`correctness` marker work. The **wrong-master path** this finding is named for is **still open**, and is closed by
Finding 4, not here; see [§ Why the reachability fix does not close Finding 1](#why-the-reachability-fix-does-not-close-finding-1),
whose reasoning is unaffected.

**Verified measurement (current tree).** `critical_path(ctx=None)` → **22 requirements**, `root_producers`
`('master_finalize',)`, 15 of 40 visited stages hollow, and `master/selection.json`, `master/edl.json`,
`master/transitions.json` all **present**. Pinned by `tests/test_ship_reachability_correctness.py` and
`tests/test_ship_reachability_observability.py`.

**Superseded measurement, kept because it is instructive.** This finding originally recorded exactly **three** stages:

```
ingest → mix → master_finalize
```

via `ingest/normalized.wav` (producer `ingest`, `required_by` `mix`) and `master/assembly.wav` (producer `mix`,
`required_by` `master_finalize`), with `full_master_ranking`, `selection_framing_apply`, `edl`, `transitions` and
`junction_snip_qa` **absent**. That was a **pre-marker** reading. It is reproducible today only by stripping the
`correctness` markers — and because a *failed contract read* used to produce the same near-empty shape, the two were
indistinguishable, which is [Finding 6](#finding-6--reachability-fails-open-when-it-cannot-read-a-contract-silent).

**Cause (historical).** `mix` declares EDL and selection as **soft**, and soft inputs never gate admissibility.

**Consequence.** `ship_reachable()` returns reachable as soon as `normalized.wav` exists, so the D1
advance-while-reachable policy advances past **every** failure in the selection→EDL chain. The output is a master mixed
from normalized source with **no selection applied** — structurally complete, schema-valid, wrong — violating the
[publishability contract](publishability-contract.md)'s "Selection leads EDL".

**The consequence survives the fix, for a different reason.** With the chain on the path, `ship_reachable()` still
reports reachable — not because the requirement is invisible, but because `edl` remains *runnable*, so nothing is
provably severed. Same wrong master, one layer down. This is the argument below, and it is why the marker work did not
close this finding.

**Reachable TODAY. No deletion required.**

**Root cause is conceptual.** One hard/soft axis answers two different questions:

| Question | Answer for `mix` + EDL/selection |
|---|---|
| Can this stage dispatch without it? | Yes — `mix` genuinely can |
| Is this required for the output to be correct? | Yes |

Reachability consumes the first answer while needing the second.

### Current `ship_reachability.py` semantics

- **`severed_requirements` requires a producer to be PROVABLY DEAD.** Severance needs **both** an open terminal defect
  for every producer **and** `producer_runnable()` false for every producer — and `producer_runnable` reads **live budget
  state** (`attempt_cap` / `count_attempts` / `exemption_for`), not a ledger row.
- **Pinned monotonicity invariant:** declaring more hard inputs can never flip a reachable run to unreachable.

### Why the reachability fix does not close Finding 1

Compose those semantics with the actual failure: **`edl` does not die — it simply never runs, while remaining perfectly
runnable.** No terminal defect, cap not spent, so `producer_runnable` is true, so there is no severance, so reachability
reports **reachable** and the walk carries on. Meanwhile `mix` proceeds regardless, because the EDL is soft *for
dispatch* and `assert_consumer` returns early when it is absent. **The wrong master is still produced.**

**Reachability was never the thing standing in the way.** It answers *"is the goal still attainable"*, not *"did the
required work actually happen"*. Putting the selection chain on the critical path is **NECESSARY** — without it a
genuinely dead selection producer cannot halt anything — but it is **NOT SUFFICIENT**, and reachability must not be
contorted into a correctness checker it was never designed to be.

**What actually closes Finding 1: Finding 4's remedy** — recording a defect when a stage **succeeds** but its output
fails `artifact_completeness.artifact_status_for_stage`. That is the only mechanism in the system that observes *"the
stage ran, and what it produced is wrong"*. It in turn requires **Finding 2's fail-open closed first**, or the net is
bypassable. Hence **`2 → 4 → 1`**.

### Design for the critical-path work — LANDED as specified

Mark **existing soft rows**; do **not** add a third input list, which would change `dispatch_delta.hard_input_paths` and
alter real dispatch behaviour.

- `required_for_correctness: true` as a marker on existing SOFT rows.
- `InputDep` gains `correctness: bool = False`.
- Helper `correctness_required(dep) -> dep.hard or dep.correctness`, as the **single** call site in
  `_contract_requirements`.
- **Minimum marker set:** `mix ← master/edl.json` + `master/selection.json`; the same pair on `master_finalize` and
  `junction_snip_qa`; and `edl ← master/transitions.json`.

All four bullets are implemented, with `dispatch_delta.hard_input_paths`, the PRESTAGE door and solver admissibility all
pinned unchanged by `tests/test_ship_reachability_correctness.py`.

### Enforcement options for `mix` — none chosen yet

Preventing `mix` from producing an assembly with no selection applied:

1. **Finding 4 route** — defect on bad output (see above).
2. **Ordering guarantee** — `mix` cannot run before selection exists.
3. **`mix` refuses when the EDL is absent** — **RISKIEST.** The `junction_recut_precedes_mix` posture depends on
   ordering flexibility in exactly this area; a hard stop here could recreate the `exec_11871` `mix` ⇄
   `junction_snip_qa` ping-pong.

## Finding 2 — PMQ fails open — CLOSED

`no_open_ship_bar_defects` caught exceptions and yielded `defects = {"open_ship_bar": 0}`, so any error while counting
defects read as **"no defects"** and publication proceeded — the final net passed precisely when it was broken.

**Landed.** PMQ now **refuses** instead. A second copy of the hole was found one layer down: `read_defect_ledger`
swallowed corrupt JSON into an empty document; it now distinguishes **absent** (legitimately zero) from
**present-but-unreadable**, raising `DefectLedgerUnreadable`.

**Leniency preserved on the WRITE path** — `record_defect` still works on a corrupt ledger so the walk keeps advancing;
only the **count gating publication** refuses. Every refusal carries `unresolved`, the underlying `error`, and an
`operator_reason`.

## Finding 3 — severity keyed on stage, not on the defect — CLOSED

`degrades_ship_bar` was a **static stage allowlist**, so whether a defect blocked depended on *which stage recorded it*
rather than *what went wrong*.

**Landed.** Severity is now a property of the defect: `defect_severity(stage, blocker, artifact, detail)`, persisted as
`ship_bar_reason`. Precedence: `SHIP_BAR_CRITICAL_STAGES` floor → blocker kind → caller-declared severity. Proven to
**only widen** (`old ⟹ new` across 19 stages × 9 blockers).

**Budget refusals (`max_*`, `attempt_memo`) are deliberately NOT widened** — a spent cap says nothing about the artifact.

## Finding 4 — the silent class — ENFORCED on ship-critical stages

A defect is recorded when a stage cannot be **dispatched**. Nothing was recorded when a stage dispatched **successfully**
and emitted a semantically wrong artifact: schema validation passes; sufficiency covers 41 of 90 contracts (and is an
inert stub — `sufficiency_enabled()` hardcodes `False`); reachability is blind (finding 1); epoch checks **freshness**,
not correctness.

**Landed — semantic-output sweep, REPORT-ONLY.** Walks every done-stamped stage's declared output through
`artifact_status_for_stage`, plus a second pass for four rule-governed artifacts no stage declares.

- Enforcement behind `MUX_DEFECT_SEMANTIC_BLOCKING=1` / `MUX_DEFECT_SEMANTIC_BLOCKING_STAGES`;
  **ratchet now includes** `full_master_ranking`, `transitions`, `edl`, `mix`, `junction_snip_qa`,
  `master_finalize`, `vo_synthesize`, `sound_design_vo_finalize`, `gap_framing_compose`,
  `mastering_research_rollup`, `topic_coverage_audit`, `narrative_arc_plan`, `sound_design_palettes`.
- **Self-healing:** it closes its own stale rows, because `resolve_stage_defects` only fires on re-dispatch and orphan
  rows have no stage to re-dispatch.
- Every finding carries its **`completeness_coverage`**, so a `schema_only` verdict is never presented as semantic.

### CORRECTION — `_gaps_*` coverage is thinner than assumed

- The table is **19 functions across 23 bindings, NOT ~30**.
- Of **71 stage outputs** on a real run: **24 get a real `gap_rule`, 40 are schema-only, 7 are bytes-only**.

**Conclusion from the worker that built it: this does NOT yet license deleting the ~11,200-line Class B carve-out.** The
sweep converts much of the silent class into the noisy one, but on roughly **half** of stage outputs it is still only
JSON-schema. The earlier hope that this fix would convert ~6,000 lines into safe deletions is **NOT supported**.

## Finding 5 — ownership unenforced for directory writes

`promote_staged_side_effects` in `write_staging.py` runs `_may_promote_pending` only on the **file** branch. The
`rel.endswith("/")` branch copies every child **unconditionally**, except a `vo_pickup` guard. A **DENY row on a
directory is documentation, not enforcement.** This matters because `solver.py` consults ownership via
`write_permitted()` to decide admissibility.

**Worse than first reported.** `_may_promote_pending` consults `write_permitted` for only **five JSON paths**, so **WAV
promotions were NEVER ownership-checked**, and two existing DENY rows — `non_owner_vo_pending_flush`,
`driver_must_not_flush_foreign_vo` — are **dead letters**.

**Illustration.** `master/transitions/` has **no ownership row at all**, yet has verified producers:

| Producer | Site |
|---|---|
| `vo_synthesize` | `stages/vo_synthesize.py:77` |
| `mix` | `stages/assembly.py:1856` → `transition_vo.py:932` |
| `junction_snip_qa` | `junction_snip_qa.py:2511` — a direct promoter call inside `remaster_mix_only`, nine lines below the `.stage_done/mix` unlink |

**Mechanism.** `run_mix` never calls `enter_stage_staging("mix")`, so its writes resolve into the **caller's** staging
tree.

**CORRECTION:** `edl` **IS** a real producer of transition WAVs via normal stage flush. The earlier
"deliberate non-producer per `edl_must_not_mint_transitions`" claim was **wrong**.

**Status.** Catalog row `master/transitions/*.wav` landed (producers `transitions`,
`vo_synthesize`, `edl`, `mix`, `junction_snip_qa`). `promote_pending` ALLOW rows for
`edl_narrative_audit`, `master_finalize`, `connector_fuse_pass`,
`connector_fuse_pass_pre_ranking`, `edl_overlap_repair`. `PROMOTE_DIR_STRICT_PREFIXES`
is armed for `master/transitions/`.

## Finding 6 — reachability fails open when it cannot READ a contract — PMQ REFUSES

**Status: OBSERVABLE — the silence is closed, the fail-open is deliberately kept.**

The two meanings are now told apart and a failed read is counted, logged and recorded. **No verdict changed**: a failed
read still resolves toward *reachable* and still cannot halt a walk, because a false UNREACHABLE throws away a shippable
tape and that remains the more expensive mistake. See [§ What landed](#what-landed) at the end of this finding.

Same fail-open class as Finding 2: an exception is converted into the answer that lets the run proceed. There, a failed
defect count read as *"no defects"* and permitted publishing. Here, a failed **contract read** reads as *"this stage
requires nothing"*, and the wrong-master reachability protection silently switches off while the run looks healthy.

### Mechanism

`_contract_requirements` (`src/interview_mux/ship_reachability.py:199`) wraps **both** the symbol imports (lines
214–219) **and** `load_contract(stage)` (line 221) in a single `try`. The handler is:

```
   222|    except Exception:
   223|        return [], True
```

That second value is `hollow`. It is **indistinguishable** from the two legitimate hollow cases — `contract is None`
(lines 224–225) and a contract that declares no correctness-required row (line 239, `return rows, not rows`).
`critical_path` (line 242) then treats hollow as *contributes nothing* and files the stage under `unknown_stages`
(lines 260–262).

The collapse is total, not partial. The walk is seeded only from `producers_for_path(MASTER_REL)`, which resolves to
`('master_finalize',)`, and `_graph_requirements('master_finalize')` is **empty** — the graph carries no
`requires`/`consumes` edge for the root. The root's requirements come **solely** from its contract, so one failed import
at the root yields **zero** requirements and a frontier that never expands.

### Why this is fail-open and not fail-closed

By design (module docstring, lines 11–28) every unknown resolves to *"not severed"*: `severed_requirements` returns `[]`
and `ship_reachable` returns `Reachability(True, False, "no_proven_severance")` (line 452). That bias is correct for a
**genuine** unknown — a false UNREACHABLE throws away a shippable tape. It is wrong when the unknown is *"our own code
did not import"*, because a failed read is scored identically to a proven absence of requirements.

**It is silent.** No log, warning, counter or telemetry is emitted on any swallow path. The module's only `ctx.log` is at
lines 490–494 inside `unreachable_halt`, and it fires only when a halt was already **proven** and then suppressed —
never when the analysis was hollowed by an error. `unknown_stages` is the sole surface, and it does not distinguish
error-hollow from declares-nothing-hollow.

### The same swallow-to-safe-answer shape elsewhere in the module

Every row below resolves toward **reachable**:

| Site | Lines | Swallowed into | Effect on the verdict |
|---|---|---|---|
| `_contract_requirements` | 222–223 | `([], True)` | stage requires nothing |
| `_graph_requirements` | 194–195 | `[]` | no graph requirements |
| `producers_for_path` | 159–160, 169–170, 177–178 | `pass` ×3 | producer list silently short; empty producers are skipped at 405–406 as "cannot prove severance" |
| `requirement_satisfied` | 298–299, 304–305 | `True` | missing/invalid artifact reads as satisfied |
| `producer_runnable` | 371–372 | `True` | dead producer reads as runnable |
| `_terminal_defect_stages` | 380–381 | `{}` | `severed_requirements` early-returns at 397–398 |
| `ship_reachable` | 441–442 | `severed = []` | reachable |
| `unreachable_halt` | 479–481 | `None` | no halt |

Two swallows lean the other way — `_revivable_by_operator` (313–314 → `""`) and `_repair_pinned` (329–330 → `False`) —
but both are only reached **after** `dead` is non-empty, so they cannot compensate for the rows above.

### Blast radius — this does not require a syntactically broken tree

- `load_contract` parses YAML from `docs/cross-cutting/stage-contracts/*.yaml`. A malformed or half-written file during
  a live edit fires 222–223 for **that stage only**.
- A **missing symbol** fires it for **every stage at once**. Realistic triggers: an in-progress guardrail deletion, a
  rename, an incomplete cherry-pick, a partially applied patch.
- The `correctness` mechanism is currently **uncommitted working-tree work** — `git show HEAD:src/interview_mux/stage_contract.py`
  contains **zero** occurrences of `correctness`, and the marker rows in `mix.yaml` / `master_finalize.yaml` /
  `junction_snip_qa.yaml` / `edl.yaml` are unstaged additions. Any operation that reverts or partially applies them
  returns reachability to the pre-marker blindness of Finding 1, silently.
- Because many call sites sit inside `except Exception: pass` shims, the missing symbol **does not crash the run**. The
  guard simply stops guarding, and the test suite stays green.

### How it already produced a wrong conclusion

Two agents reported irreconcilable readings of `critical_path()`, and the swallow is why neither could see the other was
measuring a different tree.

- **Clean re-measurement on the current tree** (`ctx=None`): **22 requirements**, `root_producers=('master_finalize',)`,
  **15 of 40 visited stages hollow**, and the selection chain — `master/selection.json`, `master/edl.json`,
  `master/transitions.json` — all **PRESENT**.
- **The other reading:** **2 requirements** (`ingest/normalized.wav`, `master/assembly.wav`), no selection chain, on
  which basis work item **W2c** was declared still blocked.
- **Reproduced in memory, no file changed:** neutralising *only* the `correctness` marker on `master/edl.json` and
  `master/selection.json` yields exactly `reqs=2` — `ingest/normalized.wav` (`required_by=mix`) and
  `master/assembly.wav` (`required_by=master_finalize`). The reported set, exactly.
- **Ruling out the import route:** deleting a symbol the 214–219 import needs, or making `load_contract` raise, yields
  **0** requirements with `hollow=1` — not 2.

So the 2-requirement reading was taken against a tree **without the correctness markers** (HEAD, or mid-edit), rather
than an import-hollowed one. Either way it describes a different tree than the one it was reported against, and the
"W2c still blocked" conclusion rests on it. Nothing in the output of either measurement said so.

### CORRECTION — Finding 1's recorded measurement is pre-marker

Finding 1 above is left as written, but as measured today the selection chain **IS** on `critical_path()`. Its
"evaluates to exactly **three** stages" is a pre-marker reading. The design under *"Design left for whoever resumes the
critical-path work"* is implemented in the working tree: `InputDep.correctness`, the `correctness_required()` helper, and
markers on `mix` (2), `master_finalize` (2), `junction_snip_qa` (2), `edl` (1). Finding 1's **substantive** argument is
unaffected — critical-path membership is necessary but **not sufficient**, and `2 → 4 → 1` still holds.

### What landed

Split the two meanings, made the failed read loud, and left every verdict alone. All in `ship_reachability.py`.

- **`_contract_requirements` returns `(rows, hollow, read_error)`.** A raised import or `load_contract` yields a non-empty
  `read_error`; `contract is None` and "declares nothing" both return `""`. `hollow` is still `True` in all three cases,
  so `unknown_stages` keeps exactly its previous meaning and no existing caller shifts underneath.
- **`CriticalPath.unreadable_stages`** — a tuple of `UnreadableContract(stage, error)`, plus a `degraded` property. The
  field is defaulted, so positional construction stays valid.
- **Loud.** `logger.warning` on each distinct (stage, error), de-duplicated so a walk re-reading the same broken contract
  cannot bury its own warning.
- **Recorded.** `halt_payload` carries an `analysis` block, and `_record_degraded_analysis` writes
  `operator/ship_reachability.json` with `reason: "analysis_degraded"` even when nothing is severed — otherwise the only
  writer is a proven severance, so this defect would stay invisible in exactly the case it fires. The block uses the
  Finding 2 shape: `unresolved`, `error`, `operator_reason`. It writes **only** when a read actually failed, so a healthy
  run is unchanged and no new artifact appears.
- **Report-only telemetry on every other swallow** — `swallow_telemetry()` counts each site and keeps the last error, so
  we learn whether these fire in practice before anyone changes what they return. `producers_for_path` (×3),
  `_graph_requirements`, the `when` evaluation, `requirement_satisfied` (×2), `producer_runnable`,
  `_terminal_defect_stages`, `ship_reachable`, `unreachable_halt` (×3), `master_committed` (×2), plus the two that lean
  toward severance (`_revivable_by_operator`, `_repair_pinned`). Return values are untouched.
- **Ownership.** `operator/ship_reachability.json` already holds an ALLOW row (`artifact_ownership.py:537`, promote row
  at 1281), so no ownership change was needed.

**Deliberately NOT done — this must not fail closed.** The fail-open is the *policy*, and only the silence was the bug.
So `MUX_SHIP_REACHABILITY_HALT` stays defaulted **off**, no new halt path exists, and an unreadable contract does not
refuse, raise or block. `tests/test_ship_reachability_observability.py` pins that directly: with the halt switch armed, a
dead producer **and** a blinded analysis, `unreachable_halt` still returns `None`.

**Known limitation, recorded rather than papered over.** `severed_requirements` returns early before `critical_path` when
no producer is terminally blocked, so on a run with nothing to prove the contracts are never read and there is nothing to
report. Reporting would mean recomputing the path on every tick, which is real cost for no signal. The guard becomes
loud at the moment severance is actually evaluated — the only moment it matters.

### Still owed

Walk halt stays default-off (a false UNREACHABLE throws away a tape). The **ship gate**
now refuses: `evaluate_post_master_quality` fails `ship_reachability_analysis` when
`critical_path().degraded` (or when the analysis itself raises). That is the Finding 2
pattern — leniency on the advance path, refusal on the gating count.

---

## Carve-out rule (durable decision)

- **Deletable (noisy).** A guard preventing a stage from **FAILING TO RUN** — the failure surfaces as a refusal, a defect
  row, and a PMQ block.
- **Carved out (silent).** A guard preventing a stage from **SUCCEEDING ON BAD DATA**.

**The carve-out still stands at ~11,200 lines.** The semantic sweep does not release it — see the `_gaps_*` coverage
correction above.

**Class B minimum ~7,644 lines:**

- `stage_input_checks.py`
- `artifact_sanitize/selection.py` + `artifact_sanitize/edl.py`
- `air_script.py` + `transitions.py`
- `artifact_repairs.py`
- `artifact_completeness._gaps_*`
