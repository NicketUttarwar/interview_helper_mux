---
name: Solver brain 0.2.0 — contract-authoritative control plane
overview: "RETIRED for authority/D14. Brain 0.2.0 seed walk shipped and is the default. Solver stage-reorder / MUX_SOLVER_AUTHORITATIVE will not ship. P3/D14 promotion retired — see HISTORY in docs/cross-cutting/mastering-homunculus.md. Body below is archival only."
todos:
  - id: p3-promote
    content: "RETIRED — authority will not ship; D14 promotion cancelled"
    status: cancelled
isProject: true
---

# RETIRED — authority / D14 will not ship

**Authority will not ship.** Brain **0.2.0** is a fixed seed walk. Solver reorder,
`MUX_SOLVER_AUTHORITATIVE`, shadow promotion, and D14 live confirmation are retired.
See HISTORY in [docs/cross-cutting/mastering-homunculus.md](../../docs/cross-cutting/mastering-homunculus.md).

The archival body below is kept for historical context only — do not treat promotion
sections as current guidance.

---

# Solver brain 0.2.0 — contract-authoritative control plane (archival)

**Thesis:** a turn budget is the symptom of *LLM owns control flow*. When the next stage is a
pure function of on-disk state, the loop terminates by construction and there is nothing to bound.

**Scope:** replaces the control layer only. All 72 stage bodies, `ctx`/`write_staging`,
`artifact_ownership`, schemas, GUI, and the ADG are kept as-is.

---

## Implementation status (2026-09-16) — read this first

This plan was written **before** implementation. Implementation found roughly twenty factual errors
in it, several load-bearing. They are corrected in place below, each marked
**`Correction (implemented):`** next to the original claim, which is kept struck or intact so the
original reasoning survives. Section numbers and cross-references are unchanged.

**Built and landed.**

- **P0** — five phase-orphans adopted and `understand` split (§3.1); tier on every contract with a
  partition test (§8.4); stage→path SSOT collapse + drift test (§8.7); test-deletion policy (§8.8).
- **P1 harness** — conformance recorder + test (§4.1), ownership cross-check (§4.2),
  `MUX_CONTRACT_REQUIRES` gate (§3.4). All three land globally, report-only by default.
- **P1.5, all six steps** (§5.6) — dispatch-door counting fix, defect ledger + `ship_reachable`,
  no-delta guard, attempt memo, two-sided precision invalidation, real critical-path reachability.
- **P2 solver** — ~~`src/interview_mux/solver.py`~~ **deleted**; authority/shadow/D14 **retired**.
- A live strand bug in brain 0.2.0 found and fixed en route — see §5.0.

**Partial.**

- **Contract population (§4.3) / D11 ratchet.** Six groups are strict at HEAD: `prepare`,
  `understand-a`, `understand-b`, `understand-c`, `plan_rank`, `sound`. `fill_gaps` is populated
  and owned (`aaad505a`) but **held**: flipping it drops `episode_structure_compose` from
  `soundscape_policy_build`'s invalidation set, and compose does not read
  `understanding/soundscape_policy.json`. `build` and `ship` stay report-only — named code
  defects in `REPORT_ONLY_REASONS`. Precision-drop inertness remains the flip gate.
- **Precision invalidation (§5.4)** is live only for stages that are conformance-green on **both**
  sides of each edge, and its result is clamped to a subsequence of the blanket set.
- **D10 gate persistence** is landed (`0e3fcd85`). Replay coverage of *historical*
  folders will not move until those runs have `gate_decisions.json`; new 0.2.0 walks
  record at the Python closers.

**Authority / D14:** **RETIRED.** Do not flip any authority env. Seed walk only.

---

## 0. Evidence this is the right fix (archival)

From `exec_11871_d19c15b58ab4_20260916T002245Z` (shipped, 11h47m, 54 code interventions):

| Observation | Value | Source |
|---|---|---|
| `max_conductor_turns` cap | 198 (= 3 × 72 stages) | `config/app.defaults.json` |
| conductor turns consumed | 198 / 198 by **01:23:30Z** — 61 min in | `mastering/homunculus/ledger.json` |
| last LLM-chosen dispatch | 01:22:45Z | ledger `source=conductor` |
| dispatches after exhaustion | 236 of 299, over 10.7 h | ledger `source=operator` |
| `mix` dispatches vs `max_mix_cycles=3` | 28, all `source=operator` | ledger |
| `junction_snip_qa` dispatches | 29, all `source=operator` | ledger |
| identical-error fingerprints | **all** `authority_denied:persist:<path>` or `seed order:` | `identical_stage_errors.json` |
| `identical_failures.json` signatures | 49, nearly all `count=0 halt=False` | `operator/identical_failures.json` |

Three conclusions that shape the design:

1. **The brain was absent for 90% of the run.** Tuning brain parameters cannot fix the thrash —
   it happened after the conductor was out of turns.
2. **Every thrash cause was a deterministic refusal**, not model wobble. Retrying an
  `authority_denied` write with a better prompt yields the identical denial. These are
   *statically decidable* facts about contracts × ownership.
3. **Caps exist and are not enforced on the driver path.** `audio_probe_build` halted correctly at
   3/3 (`limit_exhausted.json`); `mix` reached 28 against a cap of 3 ~~because the driver walk never
   consults `check_dispatch`~~. Fixing enforcement alone converts thrash into earlier halts — a
   cheaper failure, not a finished run. Hence: solver, not tuning.

   **Correction (implemented):** the driver walk **does** call `check_dispatch`. The cap was not
   bypassed, it was *miscounted*: `count_identity()` counts only identities marked **done**, and
   `junction_snip_qa` unlinks `.stage_done/mix` on every round, so `mix`'s observed count stayed at
   **0** while it burned 28 dispatches against a cap of 3. The fix was to count **ledger attempts**
   rather than done-marked identities — not to add a missing call. The conclusion ("caps did not
   bind on the driver path") survives; the mechanism in it was wrong. See §5.3.

---

## 1. What already exists (do not rebuild)

| Asset | Location | State |
|---|---|---|
| Per-stage contract schema | `stage_contract.py` — `InputDep(path, hard, producer, min_chars, when)`, `OutputDep`, `SufficiencyRule` | Shape is right, incl. `when` |
| Contract files | `docs/cross-cutting/stage-contracts/*.yaml` | ~~90 files~~ **91 `.yaml` files**, **all 72 stages covered** — `all_contract_stage_ids()` skips `_`-prefixed files, so it returns **90 ids** (`_arbiter` excluded). See the §8.4 correction |
| Dependency graph | `artifact_dependency_graph.py` — `upstream_closure`, `downstream_consumers`, `transitive_invalidate` | Works, but falls back to hardcoded `_PROPAGATION_SEEDS` |
| Ownership SSOT | `artifact_ownership.py` — `ALLOW`/`DENY`, `write_permitted()`, `owners_of()` | Authoritative, queryable |
| Write/read interception | `write_staging.py` — `resolve_write_path`, `resolve_read_path` | Single choke point for a recorder |

### 1.1 The actual gap

Contracts are structurally present but **semantically hollow**:

| Field | Populated |
|---|---|
| outputs | 79 / 90 |
| sufficiency | 41 / 90 |
| consumers | 36 / 90 |
| inputs.hard | **30 / 90** |
| propagation | **25 / 90** |
| inputs.soft | **10 / 90** |
| **fully hollow** (no inputs, no propagation, no consumers) | ~~**45 / 90**~~ **48 / 91** |

**Correction (implemented):** re-measured under this table's own definition at audit time, the
hollow count is **48 of 91 contract files**, not 45 of 90. The denominators throughout this section
are *files*; `all_contract_stage_ids()` reports 90 *ids* (§8.4). Every "45" elsewhere in this
document (§3.6, §10.1) inherits the same off-by-three.

**Correction (implemented) — `sufficiency` is not runtime-enforced.** The `41 / 90` row above, and
§2.1's `sufficiency_ok(d)` term, imply a live check. There is none: `sufficiency_enabled()` returns
`False` and `sufficiency_engine.evaluate()` returns `{"findings": []}` unconditionally. It is a
**disabled legacy stub in v2** and matters only to `verify_stage_contracts`. Treat a populated
`sufficiency` block as documentation. This matters: two workers declined a valid fix because they
believed a wrong warning derived from this claim.

`edl.yaml` declares `master/edl.json` as output and `inputs: {hard: [], soft: []}` — plainly false.
Because the graph cannot be trusted, dependency truth migrated into imperative code:

```
thrash_hardening.py       3488
delivery_guardrails.py    2904
homunculus/agenda.py      2431
stage_completion.py       2289
recovery_controller.py    1812
                        ──────
                         12924  lines, largely answering
                                "what do I do when the planner
                                 attempted something impossible"
```

That question is what the solver deletes.

---

## 2. Target architecture

### 2.1 Two planes

**Control plane — deterministic, zero LLM.**

```
admissible(stage, posture) ⟺
      tier(stage) ∈ {process, llm_full, deterministic}      # not gate/meta/volley — §8.4
  ∧   not done(stage)                                      # is_done ∧ outputs_present — §8.5
  ∧   gate_clear(stage, posture)                            # §8.1 / §8.2
  ∧   ∀ d ∈ contract(stage).inputs.hard where when(d) holds :
          committed(d.path) ∧ sufficiency_ok(d)             # committed, not staged — §8.6
  ∧   ∀ o ∈ contract(stage).outputs :
          write_permitted(stage, o.path)                    # static; see §4.2
  ∧   no unresolved invalidation claim on stage
```

Step: compute the admissible set → pick lowest seed index → **take the walk lease (§8.3)** → run →
recompute. Decision and dispatch stay separate functions so the decision half is pure.

**Correction (implemented):** the `sufficiency_ok(d)` conjunct is inert. `sufficiency_enabled()` is
`False` and `sufficiency_engine.evaluate()` returns `{"findings": []}` unconditionally — a disabled
legacy stub in v2, live only for `verify_stage_contracts` (see §1.1). The implemented rule is
`committed(d.path)` alone; sufficiency is kept in the formula as the intent, not as a check that
runs. Also see §8.3: the lease step is taken by the dispatch half, and the decision half reads the
lease **read-only** — it must not call `driver_may_walk()`.

Soft inputs never gate admissibility — hard inputs only.

**Termination is structural.** Each step either flips a stage to done (monotone progress over a
finite set) or the admissible set is empty. Empty ⇒ halt with the precise unmet `InputDep` — not a
retry. There is no unbounded loop, therefore no budget.

**Content plane — LLM.** Invoked *inside* a stage to produce artifact content, schema-validated,
bounded per artifact (the existing max-2-attempts rule). A local retry, not a global control loop.
`HomunculusBrain.prompt_tree` continues to serve this plane.

### 2.2 Reopening a done stage requires a state delta

The mix ⇄ `junction_snip_qa` ping-pong (57 dispatches, ~7 h) is a fixpoint violation. Rule:

> Invalidation is the **only** way to reopen a done stage, and the invalidator must name the
> changed artifact **and its content hash**. Same hash as the last run of that stage ⇒ no delta ⇒
> structural halt.

This is a convergence guarantee rather than a cycle cap. Stages that legitimately iterate
(recut → remaster) declare an explicit fixpoint loop with a convergence metric in their contract.

### 2.3 How each observed failure dies

| Failure class | Last run cost | Under solver |
|---|---|---|
| `authority_denied:persist:<path>` | i12–i54, ~12 h of discovery | **Commit-time test failure** (§4.2) |
| `seed order: complete X before Y` | 5 × `connector_fuse_pass`, 5 × `missing_framing` | Unreachable — never offered |
| mix ⇄ junction ping-pong | 57 dispatches | Halt on no-delta reopen (§2.2) |
| conductor turn exhaustion | brain absent 10.7 h | No turn concept exists |

---

## 3. Execution strategy — global ratchet, local work

**Not one fell swoop. Group-by-group — with exactly one global exception.**

The exception: the *test harness* (§4.1, §4.2) lands **once, globally, in report-only mode**, on day
one. A conformance test scoped to only the group being worked lets every other group rot while you
work. So: **scaffolding is global and immediate; enforcement is local and incremental.** Each group
flips its stages from `warn` to `fail` in an allowlist as it is completed, and the allowlist only
ever grows. That is the ratchet.

### 3.1 Grouping axis — the operator phases, with two fixes

Use `PHASES` in `src/interview_mux/v2/phases.py`. It already exists, ~~already drives
`PhaseWorkbench.tsx`~~, and its boundaries are already artifact cut-points. Do not invent a new
taxonomy.

**Correction (implemented): `phases.py` does not drive the GUI.** `PhaseWorkbench.tsx` imports a
**hardcoded mirror**, `frontend/src/utils/v2Phases.ts`, and the API's `v2_phases` payload is never
read by the frontend. The mirror had already drifted before this campaign — it was missing
`low_conf_island_scan` and `connector_fuse_pass`. So `phases.py` is the SSOT for the *plan's*
grouping only; any phase edit needs the mirror updated in the same change, exactly like the
`PARTIAL_*_GATES` / `partialOperatorGates.ts` pairing in §8.2. This is a third GUI-mirror SSOT, not
a derived view.

Two defects to fix first:

1. **`understand` is 23 stages — too big for one unit.** Split at artifact seams:
   - `understand-a` — transcript → segments: `source_acoustic_profile` … `segment_classification`
   - `understand-b` — segment refinement: `content_brief_reanchor` … `connector_fuse_pass`
   - `understand-c` — sonic + research + Shape: `sonic_context_build` … `mastering_plan_synthesize`
2. **Five stages map to no phase at all** — `audio_probe_build`, `framing_posture_decide`,
   `selection_order_sanitize`, `gap_report_sanitize`, `air_contract_sanitize`. This is not cosmetic:
   `gap_report_sanitize` and `air_contract_sanitize` were the i13/i14/i15 ownership battleground, and
   `audio_probe_build` was the one stage to hit its invoke cap. **Adopt them into phases before
   anything else**, or the plan has a five-stage hole exactly where the last run bled.

**Correction (implemented): the split covers 24 stages, not 23.** The "23" predates defect 2 above:
adopting `framing_posture_decide` moved it into `understand`, so `understand-a/b/c` partition **24**
stages. The two counts are consistent, not in conflict — 23 is the pre-adoption figure and 24 the
post-adoption one. The §3.2 table below is still reported at the pre-adoption boundary (67
phase-mapped stages + 5 orphans); after adoption all 72 are phase-mapped.

### 3.2 Group-by-group analysis (measured, `exec_11871`)

Excess = dispatches − stages (a clean run is 1 dispatch per stage). Hollow = contracts with no
inputs, propagation, or consumers.

| Group | Stages | Dispatches | Excess | Thrash | Hollow | Has hard inputs |
|---|---|---|---|---|---|---|
| `prepare` | 4 | 21 | 17 | 5.2× | 4/4 | 0/4 |
| `understand` | 23 | 90 | 67 | 3.9× | 11/23 | 6/23 |
| `fill_gaps` | 6 | 31 | 25 | 5.2× | 3/6 | 3/6 |
| `plan_rank` | 14 | 42 | 28 | 3.0× | 3/14 | 10/14 |
| `sound` | 2 | 4 | 2 | 2.0× | 0/2 | 1/2 |
| **`build`** | **11** | **82** | **71** | **7.5×** | **6/11** | **3/11** |
| `ship` | 7 | 24 | 17 | 3.4× | 4/7 | 2/7 |
| **total** | **67** | **294** | **227** | 4.4× | 31/67 | 25/67 |

> **227 vs 235:** this table covers only the 67 phase-mapped stages. Counting all dispatches
> (including the five phase-orphans of §3.1) gives **235** excess — the figure used in §5 and §10.1.
> The 8-point gap is itself the cost of the orphan hole.

> **Unreconciled (flagged, not corrected):** this reconciliation does not close against §0.
> §0 reports **299** total dispatches; excess over all **72** stages is then `299 − 72 = 227`, the
> same 227 the 67-stage table yields (`294 − 67`). Adding the orphans cannot raise the total to
> **235** — the five orphan stages contribute 5 dispatches *and* 5 stages. Either §0's 299 or the
> 235 is wrong by 8. **235 = 42 + 193** is the decomposition §5 and §10.1 depend on, so the two
> shares are kept as-is and the discrepancy is recorded here rather than silently patched. Re-derive
> from the ledger before quoting any of these three numbers as fact.

`build` is the prize: 11 stages burning 82 dispatches, 71 of them waste — 31% of all excess in the
run, and 6 of its 11 contracts are hollow. `plan_rank` is the healthiest starting point for
technique (10/14 already declare hard inputs).

### 3.3 Two passes, opposite directions

This is the part that must not be collapsed into a single march:

- **Contract population runs upstream-first**: `prepare` → `understand-a/b/c` → `fill_gaps` →
  `plan_rank` → `sound` → `build` → `ship`. A stage's `inputs.hard` cannot be validated until its
  producers' `outputs` are declared; declaring inputs before producers yields phantom blockers.
- **Guardrail deletion runs downstream-first** (`build` → `ship` → `plan_rank` → …), because that is
  where the mass and the payoff are — and it happens strictly **after** the solver is authoritative
  (§7), never during population.

Same groups, opposite orders, different phases of the project. Do not interleave them.

### 3.4 How 0.1.0 stays green throughout

The constraint is that **0.1.0 remains the default and must work at every commit**, in all
automation postures (manual / partial / full-auto). Checked against HEAD:

- **`propagation` and `consumers` population is effectively inert.**
  `artifact_dependency_graph.transitive_invalidate()` already walks `_downstream_in_order()` and
  returns **every** stage after `from_stage` in seed order, unioned with edges. `build_graph()` is a
  pure union of `_PROPAGATION_SEEDS` and contract edges — contracts can only *add*. So the
  invalidation blast radius is already saturated and cannot widen. Safe to populate freely.
- **`inputs[].producer` is the one live lever.** It mints `requires` edges, which feed
  `upstream_closure()` → `resolve_stage_plan().prereq_chain` → heal pins in `agenda.py` and
  `publishability_boundary.py`. Populating it *can* change 0.1.0's heal routing.
  **Mitigation:** gate `requires`-edge consumption behind `MUX_CONTRACT_REQUIRES=0` (default off) so
  population is provably inert; flip it on per group only after that group's shadow run agrees.
- `build_graph()` is `@lru_cache(maxsize=1)` — contracts load once per process. Any test that mutates
  contracts must clear the cache.

**Correction (implemented): `inputs[].producer` is NOT the one live lever, and
`MUX_CONTRACT_REQUIRES` does not make population inert.** Two consumers of contract `inputs` sit
**outside** the dependency graph and are ungated by that flag:

1. **`dispatch_delta.hard_input_paths`** reads contract `inputs` directly to build the no-delta hash
   set (§5.2). Populating contracts changed the hard-input hash set for **13 stages** and — the
   dangerous direction — **shrank** it for two: `speaker_roles` lost
   `understanding/source_topology.json`, and `vernacular_segment_sanitize` lost
   `segments/manifest.json` through own-output stripping. A shrinking hash set **refuses legitimate
   re-runs**, because a changed input that is no longer declared reads as "no delta".
   **Fix:** union the declared inputs with `FALLBACK_HARD_INPUTS`, and exempt outputs that are also
   declared inputs from own-output stripping. Monotonicity is now pinned by
   `tests/test_contract_input_declaration_safety.py` — declaring inputs may only ever grow a stage's
   hash set.
2. **`artifact_lifecycle.run_phase_checks` RAISES `ValueError` at `PRESTAGE`** when a declared hard
   input is missing or stale-stamped, and `MUX_CONTRACT_REQUIRES` does not gate that either. So
   **declaring a hard input for a conditionally-produced artifact hard-fails that stage in a live
   run.** This is the sharpest edge in the whole population task; see the four-basis rule in §4.3.

Consequently the §4 heading's "no behaviour change" is **false as written** — see the correction
there.

**Also note (contradiction between this section and §5.4):** the first bullet's inertness argument
— "the blast radius is already saturated and cannot widen, so `propagation` / `consumers` are safe
to populate freely" — **expires the moment §5.4 ships**. Precision invalidation makes those exact
fields *subtractive*: a populated `consumers` list can now shrink what gets invalidated, which is
the one direction that can leave a stale artifact behind. Since §5.4 has landed, populate
`propagation` / `consumers` under the §5.4 rules (two-sided conformance gate, clamped to a
subsequence of the blanket set) — **not** "freely".

**Corollary worth its own ticket:** `transitive_invalidate` returning *everything downstream* is
itself a thrash engine — one stale artifact reopens the rest of the pipeline. Precision invalidation
from real contract edges is a large part of the win, and it is only safe once §4.1 conformance proves
the edges are complete.

### 3.5 Definition of done, per group

A group is complete when all five hold. No group starts before the previous one is complete.

1. Zero hollow contracts in the group; `when` predicates populated for conditional inputs.
2. Conformance test (§4.1) passes in **fail** mode for the group's stages — observed reads/writes ⊆ declared.
3. Ownership cross-check (§4.2) passes for the group's outputs.
4. Solver (§6.1) proposes the same stage as the driver for the group's stages across one full run in shadow.
5. `pytest tests/` green; `./scripts/verify_artifact_contract.sh` green; **0.1.0 still default and still ships a master.**

**Correction (implemented): item 4 makes Phase 1 uncompletable by this document's own definition.**
The solver does not exist until Phase 2 (§6.1), and Phase 1 (§4) is sequenced before it — so while
Phase 1 runs, **no group can satisfy all five conditions and therefore no group can be marked
complete**. The plan's own ratchet stalls at group one. Resolution used: items **1, 2, 3 and 5** are
the achievable **Phase 1 bar** and a group is "population-complete" on those four. Item 4 is a
**Phase 2 promotion gate**, checked per group once the solver exists and before that group's
guardrail subtraction (§7). Note also that item 4's "one full run in shadow" is blocked on the
real run that has not happened — see the status section at the top.

### 3.6 Why not one fell swoop

~~45~~ **48** hollow contracts (§1.1 correction) whose real dependencies are conditional, ~13k lines of guardrails encoding
undocumented lessons, and an 11h47m full-auto run as the only true integration test. A big-bang
cutover has no intermediate verification, no way to attribute a regression to a specific contract,
and no way to keep 0.1.0 shippable while it is in flight. The repo's own precedent agrees: the
End-A…F predicate ledger works **one family per turn** with a fixed queue and per-family fixtures.
This plan is that protocol applied to contracts instead of predicates.

---

## 4. Phase 1 — make contracts true (~~no behavior change~~ **behaviour-affecting**)

Ship this phase even if 0.2.0 never lands; it is pure risk reduction.
**Sequencing for this phase is §3** — global harness first, then group by group, upstream-first.

**Correction (implemented): Phase 1 is not behaviour-neutral.** The heading's promise rested on
`MUX_CONTRACT_REQUIRES` gating contract consumption. It does not. Contract `inputs` are read
outside the dependency graph by `dispatch_delta.hard_input_paths` (no-delta hash sets, §5.2) and by
`artifact_lifecycle.run_phase_checks`, which **raises `ValueError` at `PRESTAGE`** on a missing or
stale-stamped declared hard input. Populating contracts therefore changes live behaviour on both
paths — it changed hard-input hash sets for 13 stages and shrank two. Full detail and the fix
(union with `FALLBACK_HARD_INPUTS`, own-output exemption, monotonicity test) are in the §3.4
correction. Phase 1 remains worth shipping alone; it is risk reduction, not a no-op.

### 4.1 Runtime conformance recorder

Instrument `write_staging.resolve_write_path` / `resolve_read_path` behind
`MUX_CONTRACT_RECORD=1`. Emit `operator/contract_observed.json` as `{stage: {reads: [], writes: []}}`.
Test asserts observed ⊆ declared, and reports declared-but-never-touched as warnings.
`docs/cross-cutting/stage-contracts/_extracted_deps.json` is a crude static precursor (26 entries) —
supersede it.

### 4.2 Static ownership cross-check

~~`write_permitted(ctx, path, stage_key, ...)` guards every `ctx` use behind `if ctx is not None`, so it
runs statically with `ctx=None` — no run dir needed:~~

```python
# ORIGINAL SKETCH — do not copy; ctx=None silently skips the epoch rows (correction below)
for sid in all_contract_stage_ids():
    for out in load_contract(sid).outputs:
        ok, reason = write_permitted(None, out.path, sid)   # artifact_ownership
        assert ok, f"{sid} declares {out.path} without an ALLOW row: {reason}"
```

**Correction (implemented): `ctx=None` is wrong here.** The seat and freeze-epoch rows in the
ownership catalog need `current_epoch(ctx)`. With `ctx=None` the `if ctx is not None` guard makes
those rows evaluate vacuously, so the cross-check **silently ignores the delivery-epoch boundary**
and passes outputs it should reject. The landed test
(`tests/test_contract_ownership_xcheck.py`) supplies a ctx so `current_epoch(ctx)` resolves, and
iterates the **tier-partitioned** stage set rather than all ids (§8.4).

Note `fail_closed()` governs unknown-path behaviour; assert with it **on** so a contract output
missing from the catalog fails rather than passes silently.

**This test alone would have caught i12–i54 at commit time.** Land it first.

### 4.3 Populate the ~~45~~ **48** hollow contracts

Hardest and highest-value task. Sources, in order of trust: the conformance recorder from a real
run, then `_PROPAGATION_SEEDS` in `artifact_dependency_graph.py`, then the `from_stage` / heal-pin
tables in `stage_completion.py` (`PRODUCER_PIN_TABLE`) — that code *is* the dependency knowledge,
transcribed imperatively.

**`when` predicates are the crux.** Contracts are hollow partly because real dependencies are
conditional on `framing_full` vs not, `narrative_mode`, and montage grammar. `InputDep.when` already
exists as a `dict` field. Define a deliberately small predicate language — `{key: value}` matched
against run_meta + mastering plan, no expressions — and refuse to grow it. A naive rewrite fails
exactly here.

**Correction (implemented) — three population rules the plan did not know.** Each cost real
debugging; none is optional.

1. **Hard vs soft is a four-basis test, not "conditionally present ⇒ soft".** Because
   `run_phase_checks` raises at `PRESTAGE` on a missing declared hard input (§3.4), the tempting
   blanket rule is "anything conditionally present must be soft". That rule is too blunt and
   **caused a real regression when applied**: downgrading three `transcript/full.json` hard inputs
   dropped the transcript out of `hard_input_paths`, which would stop G0 corrections from
   re-triggering those stages — the no-delta guard would see no delta in a transcript the operator
   had just fixed. The working rule: an input may be **hard** on any one of four bases —
   **preflight-backed**, **refuses-backed**, **`when`-gated**, or **unconditional presence**.
   Anything else is soft.
2. **A read is not always a `producer` edge.** Some stages legitimately read artifacts produced
   **downstream** of themselves on re-entry (the read-modify-write pattern generalises beyond the
   cases already known). Attaching a `producer` to such a read mints a **forward `requires` edge** —
   a phantom blocker by construction, which is the §3.3 failure mode arriving from the other
   direction. **Declare those reads without a producer.**
3. **Declared inputs may only grow a stage's hard-input hash set.** Enforced by
   `tests/test_contract_input_declaration_safety.py` (§3.4).

**Exit criteria:** conformance test green on a full run; zero hollow contracts; `_PROPAGATION_SEEDS`
deleted and the ADG reading contracts only.

**Status:** only the `prepare` group is proven strict; every other group is populated but
report-only, and no full run has exercised the conformance test. See the status section at the top.

---

## 5. Phase 1.5 — the driver-side 82% (0.2.0 thrash completion)

Removing the conductor (shipped) eliminated only **42 of 235** excess dispatches (17.9%). The other
**193 (82.1%)** were issued by the deterministic driver walk and are untouched by it. This phase is
what makes 0.2.0 actually thrash-free, and it is **independent of the solver** — it needs no LLM
decision at all.

### 5.0 Recorded decisions

| # | Decision | Chosen |
|---|---|---|
| **D1** | Behaviour when a stage cannot progress | **Advance past it while the ship bar is provably reachable**, recording a defect. Halt only when `master.wav` becomes provably unreachable. |
| **D2** | Whole-tail invalidation | **Replace with contract-derived precision edges now** (see §5.4 for the safety gate). |
| **D3** | Rollout | **0.2.0 stays default** and improves incrementally. |

D1 is the north star for this phase: *progress toward `master.wav` is the objective; halting is the
exception and must be justified by unreachability, not by a failed attempt.*

**Operator decisions taken during implementation (2026-09-16).** These extend D1–D3; the original
three are unchanged.

| # | Decision | Chosen |
|---|---|---|
| **D4** | Shadow logging default | **ON** (`MUX_SOLVER_SHADOW`) — the disagreement log is free and is the only way the promotion gate can ever be met. |
| **D5** | Solver authority default | **OFF** (`MUX_SOLVER_AUTHORITATIVE`). Promotion requires **zero non-deferred disagreement on a real run** (§6.2). |
| **D6** | Reachability halting default | **OFF** (`MUX_SHIP_REACHABILITY_HALT`) — the shipped default must not halt a run that would otherwise have shipped. Consistent with D1's "unknown ⇒ reachable" (§5.5). |
| **D7** | Guardrail subtraction (§7 step 4) | **Authorised WHOLESALE**, and the "every deletion cites the contract rule that replaces it" requirement is **WAIVED**. Holes are patched in a later pass and recorded in `docs/cross-cutting/subtraction-holes.md`. |
| **D8** | Pinned forensics tests under subtraction | **Never deleted**, and **allowed to fail** — the failing set *is* the hole map (§8.8 unchanged otherwise). |
| **D9** | Validation run | **None.** No fresh full-auto run is made while the forensics campaign is open, so every claim below is static analysis plus the test suite. |

**Correction (implemented) — a live strand bug in 0.2.0, now fixed.** Not anticipated by this plan:
`recovery_allowed` waited on an `analyze_issue` verdict that **only the conductor tool loop
produces**. Under the deterministic control plane there is no conductor, so every novel failure was
deferred to an analysis that could never arrive — the run stranded rather than recovering. This is
the shape of bug to look for wherever 0.2.0 inherited a predicate written for the LLM plane.

### 5.1 Measured mechanisms (exec_11871, driver/rerun dispatches only)

| Mechanism | Stages | Excess | Share |
|---|---|---|---|
| **M1** No-delta repair loop | `junction_snip_qa` 28 + `mix` 27 | **55** | 28.5% |
| **M2** Re-walk of the same incomplete set on driver re-entry | `missing_framing` 22, `vernacular_segment_sanitize` 14, `connector_fuse_pass` 12, `speaker_roles` 11, `mastering_research_waves` 10 | **69** | 35.8% |
| **M3** Backward rewinds from whole-tail invalidation | `master_finalize` 8, `information_package_plan` 7, `selection_framing_apply` 7, `transitions` 7, `edl` 7, `nugget_layup_compose` 7, `podcast_publish` 6 | **~49** | 25.4% |

Driver re-entry counts that enabled M2: **148** `delivery_walk_to_master` + **63**
`analysis_fill_delivery_prereqs` — each re-entry recomputed `remaining` and walked the same set again.

### 5.2 M1 — dispatch requires a state delta

Every dispatch records `(stage, hash_set_of_declared_hard_inputs)`. A re-dispatch whose hash set is
**identical** to the last attempt is refused as `no_delta` — the inputs did not change, so the
outcome cannot. This is the fixpoint rule from §2.2, enforced at the dispatch door rather than
trusted to a cap.

`mix` ⇄ `junction_snip_qa` ping-ponged for ~7 h with no input change between iterations. Under this
rule the second iteration is refused and the run goes to §5.5 reachability instead of looping.

A `no_delta` refusal is **not** an error: it feeds reachability (D1). Legitimate iteration declares a
convergence metric in its contract (§2.2) and passes a changed input each cycle by construction.

**Correction (implemented): the guard is only as sharp as the declared hard inputs.** Where a stage
declares none — still the majority — there is no hash set to compare, and the guard falls back to a
weaker **state-token** witness that cannot tell "same inputs, will fail identically" from "genuinely
new attempt". Those re-dispatches pass the door. This is why the §5.6 target is corrected from
`< 10` to 40–55, and why closing the rest is §4.3 population work rather than §5 work. Two further
hazards live here, both landed: the hash set must be **monotone** under declaration (it shrank for
two stages during population), and own-output stripping must exempt artifacts that are also
declared inputs — see §3.4.

### 5.3 M2 — one dispatch door, and no re-offering unchanged stages

~~Two~~ **Three** mechanical fixes (the list below has always had three items), which close caps
that **already exist and are simply ~~bypassed~~ miscounted** — see item 1:

1. ~~**Route the driver walk through `check_dispatch`.**~~ **Correction (implemented): the driver
   walk already calls `check_dispatch`.** The premise of this item is false, though its conclusion
   is not. `mix` reached 28 dispatches against `max_mix_cycles: 3` and `junction_snip_qa` 29 against
   `max_invokes_per_identity: 3` **with the cap check running on every one of them**. The defect is
   in the counter: **`count_identity()` counts only identities marked done**, and
   `junction_snip_qa` unlinks `.stage_done/mix` each round, so `mix`'s count read **0** forever —
   the cap was consulted and always found headroom. `audio_probe_build` halted correctly at 3/3
   only because nothing unlinked its marker.
   **Landed fix: count ledger attempts, not done-marked identities.** No new call site, no new
   door; the door was already there and was being told the wrong number. Anyone reading this item
   literally would go looking for a missing call that does not exist.
2. **Audit the budget exemptions.** `check_dispatch` early-returns on
   `policy_remediation_active(ctx)` and `cta_cover_budget_exempt(ctx)`, voiding every cap. Narrow
   each to a named stage set, log every exemption taken, and add a test that an exemption cannot
   cover an audio-mutating stage.
3. **Per-re-entry attempt memo.** A stage attempted in this walk whose inputs are unchanged is not
   re-offered on the next driver re-entry. This is what stops 148 re-entries from re-walking the
   same remaining set.

### 5.4 M3 — precision invalidation (D2), safely

`transitive_invalidate()` currently unions `_downstream_in_order()`, i.e. **every** stage after the
source, so one stale artifact reopens the rest of the pipeline. Replace it with contract
`propagation` / `consumers` / `requires` edges.

**Correction (implemented): precision invalidation does NOT remove the M3 rewinds.** Measured at
full conformance-green across all 72 stages, precision drops **42 of 1420 stage-slots (3.0%)** —
and for the **seven stages that actually produced the ~49 backward rewinds in §5.1, the
invalidation set does not shrink at all.** The delivery tail is a *chain*: nearly every stage after
the source really is downstream of it, so the blanket walk was already close to correct there.
Those ~49 rewinds are therefore **not** §5.4's to collect. They belong to **§5.2** (no-delta),
**§5.3** (attempt memo) and **§5.5** (reachability), which is where the §10.1 arithmetic should
attribute them.

Where precision does pay is **cheap upstream analysis stages**, whose fan-out is genuinely narrow:

| Source stage | Blanket | Precise |
|---|---|---|
| `selection_order_sanitize` | 31 | 22 |
| `audio_probe_build` | 30 | 24 |
| `gap_report_sanitize` | 26 | 21 |
| `content_brief_reanchor` | 20 | 16 |

The mechanism is still worth having — re-running 22 stages instead of 31 on an early correction is
real operator time — but bank it as **a cheaper G0-correction loop, not as thrash removal.** The
§5.1 M3 row and its 25.4% share stand as a measurement; only the attribution to this section was
wrong.

**How "precision now" lands without risking a stale master:** the mechanism ships immediately, but
activates **per stage**, gated on ~~that stage's~~ contract being conformance-green (§4.1) and
ownership-clean (§4.2). Stages not yet green keep whole-tail behaviour. So precision spreads exactly
as fast as the contracts become trustworthy, and there is never a window where an unproven edge set
decides what to invalidate.

**Correction (implemented): a source-side-only gate is unsound.** As written, the gate checks the
conformance of the stage being invalidated *from*. But dropping stage **S** from the invalidation
set is a claim that **S's declared inputs are complete** — and only **S's own** conformance
evidence can support that. The source's greenness says nothing about what S secretly reads.

Concrete near-miss caught in implementation: `audio_probe_build` is conformance-green and its
contract names four consumers, so a source-side gate dropped `content_context`,
`talking_points_compose`, `ideal_cuts_propose` and `speaker_roles` from its invalidation set. All
four really do read `transcript/protected_zones.json`, via
`stage_input_helpers.transcript_quality_for_ctx` — a read **no contract mentions**. Under a
source-side gate those four keep stale derivations after a probe change.

Two requirements, both landed:

- **The gate is two-sided.** A consumer is dropped only when the source **and** that consumer are
  both conformance-green.
- **The precise result is clamped to a subsequence of today's blanket set.** Precision may only
  ever *remove* stages, never add or reorder. Without the clamp, contract edges made
  `audio_probe_build` **expand from 30 to 60** stages — precision invalidation doubling the blast
  radius it exists to shrink.

Two hard safety rails, both required before any audio stage goes precise:

- **Audio stages stay whole-tail until proven.** Every stage in `AUDIO_MUTATING` keeps whole-tail
  invalidation until its contract is conformance-green **and** a fixture proves the precise edge set
  is a superset of the observed consumer set.
- **Epoch assertion at the seal.** `verify_master` must assert `master.wav` derives from the current
  EDL/mix epoch. Under-invalidation then fails loudly at the ship gate instead of shipping stale
  audio — this is the backstop for the one failure mode precision invalidation can introduce.

### 5.5 The new machinery D1 requires

**`ship_reachable(ctx) -> Reachability`** — the load-bearing predicate. `master.wav` is reachable iff
every stage on the critical path to `master_finalize` is either done-and-complete, or admissible with
a state delta, or **skippable without degrading the ship bar** per
[publishability-contract.md](../../docs/cross-cutting/publishability-contract.md).

> **Conservative by construction:** unknown ⇒ reachable. D1 favours progression, so an
> indeterminate answer must never halt a healthy run. Only a *proven* unreachable path halts.

**Correction (implemented, D6 in §5.0):** the real critical-path analysis landed, but its ability
to **halt** is behind `MUX_SHIP_REACHABILITY_HALT`, **default OFF**. The shipped default therefore
cannot halt a run that would otherwise have shipped; unreachability is recorded in the defect
ledger and surfaced, not enforced. Turning it on is a deliberate, separately-decided step.

**`operator/defect_ledger.json`** — every advance-past records the stage, the blocker, the artifact,
and whether it degrades the ship bar. This is the audit trail that replaces thrash: the run keeps
moving, and nothing is silently forgotten. It is a **publishability input** — PMQ must refuse
`publish_allowed` when any ship-bar-degrading defect is open, which is what keeps D1 from quietly
shipping a hollow master. Needs an ALLOW row (`operational`).

**Halt payload.** When reachability is provably false, halt with the unmet dependency, its producer,
and a resume pin — per §10.2, the halt message is the product.

### 5.6 Order of work

Safest-first, so each step is independently shippable with 0.2.0 as default (D3):

1. **§5.3 budget unification + exemption audit** — mechanical, uses existing caps, no new semantics.
2. **§5.5 defect ledger + `ship_reachable`** (conservative stub: always reachable) — pure telemetry,
   zero behaviour change, and it instruments what the next steps need.
3. **§5.2 no-delta guard** — now safe, because a refusal has somewhere to go (ledger + reachability).
4. **§5.3 attempt memo** — kills the re-walk once refusals are recorded.
5. **§5.4 precision invalidation** — per-group activation as conformance goes green; audio last.
6. Tighten `ship_reachable` from stub to real critical-path analysis, with the epoch assertion live.

~~**Target for this phase alone:** driver/rerun excess **193 → < 10**, without the solver.~~

**Correction (implemented): `< 10` is not reachable in this tree.** The measured expectation from
the four P1.5 steps is **140–155 of 193 removed**, leaving roughly **40–55**. The reason is
structural: the no-delta guard (§5.2) is only as sharp as the declared hard inputs, and **only a
minority of stages declare any**. For the rest the guard falls back to a weaker **state-token**
witness, which cannot distinguish "same inputs, will fail identically" from "genuinely new
attempt", so those re-dispatches survive the door. Closing the remaining gap is contract-population
work (§4.3), not §5 work — and the §10.1 target row is corrected to match.

---

## 6. Phase 2 — solver in shadow mode

### 6.1 Build

~~New module `src/interview_mux/solver/plan.py`~~ **Landed as a flat module,
`src/interview_mux/solver.py`** — no package, no `plan.py`; every reference to `solver/plan.py`
means this file (~300–500 lines). Reads **only** contracts, ownership,
and on-disk state. Pure and unit-testable: given a fixture run dir, assert the admissible set.
No `ctx` mutation, no LLM, no network.

```
next_stage(ctx) -> Decision(stage | halt(blockers: list[UnmetDep]))
```

### 6.2 Shadow

Behind `MUX_SOLVER_SHADOW` (**default ON**, per D5 in §5.0), the current driver stays
authoritative; the solver computes its choice at each dispatch and logs both to
~~`operator/solver_shadow.jsonl`~~ **`operator/solver_decision.jsonl`**. Disagreements are the work
queue — each one is either a contract bug (fix the YAML) or a real guardrail rule not yet expressed
declaratively (fix the solver).

**Correction (implemented): one artifact, not two.** This section and §10.2 named
`solver_shadow.jsonl` and `solver_decision.jsonl` for the same log. There is **one**:
**`operator/solver_decision.jsonl`**, carrying both the shadow comparison and the per-step decision
/ halt payload. `solver_shadow.jsonl` is struck everywhere it appears (here and in §10's ownership
note) and no such artifact exists or should be created.

**Promotion gate:** one full-auto run, **zero non-deferred disagreements**, on the tape from §0.
`MUX_SOLVER_AUTHORITATIVE` defaults OFF until then (D5). **Not met:** no such run has been made and
none will be while the forensics campaign is open (D9).

### 6.3 Replay harness

Replay `exec_11871`'s ledger against the solver offline: it must never propose a stage whose actual
dispatch produced `authority_denied` or `seed order`. Cheap regression corpus with a known answer.

---

## 7. Phase 3 — promote and subtract

1. **Register the brain — ✅ DONE (2026-09-16).** `0.2.0` is registered in `version.py` and
   `docs/homunculus/versions.yaml` and is **default** (`default_version: "latest"` →
   `highest_version()`). Per **D3** it stays default while §5 lands.
   **Deviation from the original plan, deliberately:** `kind` stays `homunculus` and control flow is
   selected by a new `control_plane` field (`llm` | `deterministic`). A new `kind="solver"` would
   make `is_homunculus_brain()` false at all 22 `is_homunculus_run` sites — including
   `pipeline.py:593`, which wraps stages in `dispatch_stage` — silently dropping the ledger, admit
   rails, and dispatch budgets on the new default brain.
   *Still open:* extend `HomunculusBrain` with an optional `limits` dict (caps are global in
   `mastering.homunculus.limits` today), and split `is_homunculus_run` into capability predicates so
   rails and control flow are no longer one flag.
2. **Route every dispatch through one door.** Driver-walk and conductor paths both call the solver.
   **Brought forward to §5.3** — it is the fix for `mix` at 28 vs cap 3 and does not need the solver.
3. **Demote the LLM** to content-only: drop `schedule_stage`, `skip_stage`, `walk_seed_remainder`
   from the tool catalog in `homunculus/registry.py`. `rerun_stage` / `invalidate_downstream` survive
   only with a content-hash delta per §2.2.
4. **Subtract.** Delete superseded code in `thrash_hardening.py`, `delivery_guardrails.py`,
   `agenda.py`, `recovery_controller.py`. ~~**Rule: every deletion must cite the contract rule that
   replaces it, in the commit message.**~~ Target ~12–16k lines out, ~1–2k in.

   **Correction (operator decision, D7/D8 in §5.0) — authorised but NOT executed.** Subtraction is
   authorised **wholesale**, and the cite-the-replacing-contract-rule requirement is **waived**:
   demanding a citation per deletion makes the pass unaffordable against ~13k lines whose rules
   were never written down. Instead, holes are patched in a **later pass** and each is recorded in
   `docs/cross-cutting/subtraction-holes.md`. **Pinned forensics tests are never deleted and are
   allowed to fail** — the failing set is the hole map (this refines §8.8: the "never delete"
   bucket stands; "must stay green through subtraction" does not). Nothing has been deleted yet.

---

## 8. Footguns — mandatory preconditions

Each of these is a way the plan as written would break something real. **All are blocking: resolve
before the group that touches them.**

### 8.1 Gates are missing from the admissibility rule

§2.1 has no gate term, so the solver would run straight through **G0 / G-Framing / G1 / Preclean /
G-Publish**. `homunculus/gates.py` defines 10 `CATEGORIES` (`transcript_integrity`,
`framing_consent`, `vo_pickup`, `source_preclean`, …) and `category_status()` exposes
`open` / `blocks_analysis`. `phases.py` carries gates as first-class entries
(`transcript_review`, `g1_vo_pickup`, `g_publish`), and **`transcript_review` and `g1_vo_pickup`
already have contract files**. Fix the rule:

```
admissible(stage) ⟺ … ∧ gate_clear(stage, posture)
```

~~`audio_preclean` is gated too (`source_preclean` — *never auto-run*, offer only).~~

**Correction (implemented): Preclean is not an ordinary blocking gate, and treating it as one
deadlocks the pipeline.** `audio_preclean` **self-skips** — when the operator has not opted in it
writes `preclean/skip.json` and completes. So refusing to *dispatch* the stage until a gate clears
does not pause the run, it **strands every downstream stage**: the stage never runs, never writes
`skip.json`, and nothing after it becomes admissible. Measured against all three postures (manual,
partially-accelerated, full-auto), a blocking `gate_clear` term on `audio_preclean` deadlocks every
one of them.

**The thing that must never be automatic is the DeepFilterNet *enable*, not the stage.** The stage
is always admissible; the gate governs the *parameter* it reads. The other five gates
(G0 / G-Framing / G1 / G-Publish and the rest of §8.1) are unaffected — they are genuine blocking
gates and the `gate_clear(stage, posture)` term is correct for them.

### 8.2 Posture is missing — this is the "partially accelerated" requirement

`automation_run.py` is the SSOT: `is_partially_accelerated_run(meta)`, `is_full_auto_run(meta)`,
and critically

```python
PARTIAL_MUST_ACT_GATES = ("transcript_review", "g_publish")          # operator must act
PARTIAL_MAY_PAUSE_GATES = ("gap_framing", "missing_framing",
                           "g1_vo_pickup", "stage_reuse", "write_approval")
```

**The admissible set is a function of `(state, posture)`, not state alone.** A solver that ignores
`run_mode` will auto-advance `transcript_review` in partially-accelerated mode and silently
destroy the G0 contract. Signature must be `next_stage(ctx, posture)`, with a test per posture
(manual / partially-accelerated / full-auto) for every group.

**Second SSOT warning:** `PARTIAL_*_GATES` is explicitly "a mirror of
`frontend/src/utils/partialOperatorGates.ts`". Any gate change needs both sides plus a parity test,
or the GUI and solver disagree about who must act.

### 8.3 Concurrency — the solver must take the lease

Two actors walk the pipeline: the GUI and the automation driver. They single-flight through
`operator/gate_advance_lease.json` with a **20 s TTL** (`GATE_ADVANCE_LEASE_TTL_SEC`), ~~arbitrated by
`driver_may_walk(ctx)` → `gui_holds_fresh_lease()` + `_job_is_running()`~~. A solver that computes
"next admissible stage" without taking the lease will double-dispatch against an operator clicking
Continue. Also preserve `check_audio_serialize` — `AUDIO_MUTATING` stages must stay
one-at-a-time or two MLX/ffmpeg jobs contend for the same device.

**Rule: the solver decides; it never dispatches without the lease.** Keep decision and dispatch as
separate functions so the pure part stays unit-testable (§6.1).

**Correction (implemented): do NOT call `driver_may_walk()` from the admissibility decision.**
`driver_may_walk(ctx)` does not merely *read* the arbitration state — it **ends by acquiring the
lease** (`take_gate_advance_lease`). Calling it from a decision function would make a pure function
impure, and worse, would have the solver **take the lease merely by thinking about it**, racing an
operator who is clicking Continue. That is precisely the bug this section exists to prevent, so
following §8.3 literally would have caused it.

**What landed:** the decision half **mirrors `gui_holds_fresh_lease()` read-only** and takes
nothing. Acquisition stays in the dispatch half, as the rule above already says. Note also that
`_job_is_running()`'s two branches **both return `False`** in the current tree, so it contributes
nothing to arbitration — **a fresh GUI lease is the whole answer**, and a read-only mirror of that
one predicate is a complete substitute for `driver_may_walk` at decision time.

### 8.4 `all_contract_stage_ids()` returns 90, not 72

**Correction (implemented): the partition is 72 pipeline stages + 18 non-stages, not 19.**
`all_contract_stage_ids()` globs `*.yaml` and **skips `_`-prefixed files**, so `_arbiter` — the
`meta` row in the table below — is **never returned**. Of 91 `.yaml` files in
`docs/cross-cutting/stage-contracts/`, the function yields **90 ids = 72 + 18**. The §4.2 loop
iterates **18** non-stages, and any test asserting a 19-way non-stage set will fail on the
`_arbiter` row that is not there. (Heading count kept as-is because it is cross-referenced; the
arithmetic beneath it is the corrected version.)

The §4.2 loop as written would iterate ~~19~~ **18** non-stages and emit false failures:

| Kind | Examples |
|---|---|
| meta | ~~`_arbiter`~~ — excluded by the `_`-prefix skip; never reaches the loop |
| gates | `transcript_review`, `g1_vo_pickup` |
| sub-stage volleys | `ranking_refine`, `transitions_refine`, `narrative_arc_refine`, `sdp_intent_refine`, `sfx_prompt_refine`, `edl_narrative_refine` |
| adjudicators | `connector_seam_adjudicate`, `island_cluster_structure_adjudicate`, `junction_thought_complete`, `junction_feel_audit` |
| briefs / init / ingest | `sfx_brief`, `podcast_sfx_brief`, `sound_design_plan_init`, `vo_ingest`, `synthetic_framing_plan` |
| retired | `optimal_questions` |

`StageContract.tier` already exists with exactly the right values
(`llm_full | deterministic | gate | process | meta`). **Precondition: every contract declares a
correct `tier`, and the solver + x-check partition on it.** Add a test that every contract's tier is
set and that the `process`/`llm_full`/`deterministic` set equals the 72 pipeline stages.

### 8.5 `done()` must not trust `.stage_done`

Hollow markers are real and were observed in the reference run: 8 stages had `.stage_done` with no
ledger dispatch row. `_block_hollow_skip` and `stage_outputs_present` exist for this reason.

```
done(stage) ⟺ ctx.is_done(stage) ∧ stage_outputs_present(ctx, stage)
```

A solver trusting the marker alone will declare inputs satisfied from artifacts that do not exist.

### 8.6 `exists()` is ambiguous — staged vs committed

`write_staging` distinguishes staged from committed (`staged_path`, `resolve_read_path`,
`artifact_exists_resolved`, `uncommitted_pending_reason`, promotion). **Admissibility must read
committed state only** (`artifact_exists_resolved` semantics, and refuse when
`uncommitted_pending_reason` is set). Otherwise a stage becomes admissible off another stage's
un-promoted staging directory — a race that produces artifacts derived from work that may never
commit.

### 8.7 Three SSOTs for stage → path (contracts would be a fourth)

`STAGE_ARTIFACT_DISK_PATHS` (`prompt_validation`), the `artifact_ownership` catalog, and stage
contract `outputs` all claim this. `build_graph()` already merges the first and third.
**Precondition: one direction of truth + a drift test** asserting the three agree, landed with §4.2.
Without it, populating contracts creates a fourth competing truth and the plan makes things worse.

**Correction (implemented): the three sources already agreed on all 72 primary outputs.** The
premise that they disagree is false, and for a structural reason worth keeping: contract `outputs`
are **generated from** `STAGE_ARTIFACT_DISK_PATHS`, and the ownership catalog **mirrors** it. They
are not three independent claims about primary paths — they are one claim and two derivations, so
"collapse the SSOT" was largely already true. Real drift existed only on **secondary outputs**,
which are hand-written and derive from nothing.

The drift test still landed (`tests/test_path_ssot_drift.py`) and is still worth having, but
re-scope the expectation: it protects **secondary outputs** and guards the generator relationship
from decaying. It is not the primary-path reconciliation this section imagined, and this footgun
was not blocking.

### 8.8 Test-deletion policy — 3,650 tests across 530 files

Subtraction (§7, step 4) will break tests asserting today's repair behavior. Classify before deleting:

- **Pinned lessons — never delete.** `MUX_FORENSICS=0` cascade fixtures from i1–i54 and the
  F\*/H\*/End-\* families. These encode invariants, not implementation. If one fails under the
  solver, the solver is wrong.
- **Scaffolding — delete with its code.** Tests asserting a specific heal route, pin table entry, or
  retry count that the contract now decides.

Rule: a deletion PR touching tests must list which bucket each test is in. Making a build green by
deleting the forensics corpus is the single worst outcome available here.

**Correction (operator decision, D8 in §5.0):** the "never delete" bucket stands and is
strengthened — pinned forensics tests are **never deleted**. What is relaxed is the implicit
expectation that they stay **green** through subtraction: under the wholesale subtraction
authorised in §7 step 4 they are **allowed to fail**, and the failing set is the hole map, patched
in a later pass and recorded in `docs/cross-cutting/subtraction-holes.md`. A red pinned test after
subtraction is a logged hole, not a licence to delete it.

### 8.9 Iteration cost — do not put a 12 h run in the inner loop

The reference run was **11 h 47 m**. §6.2's "one full run, zero disagreements" is a *release* gate,
not a dev loop. Required cheaper tiers, in order of use:

1. Fixture run-dirs — synthetic `exec_*` trees, millisecond assertions on the admissible set.
2. Ledger replay (§6.3) against `exec_11871` — the solver must never propose a stage whose real
   dispatch produced `authority_denied` or `seed order`.
3. One live full-auto per group boundary, not per commit.

### 8.10 No per-group rollback

Add a per-group flag (e.g. `MUX_CONTRACT_STRICT_GROUPS=prepare,plan_rank`) so one bad group reverts
without reverting the campaign, and so a half-migrated repo is always shippable.

### 8.11 Dead flow branches

`FLOW2_ORDER` / `FLOW3_ORDER` in `pipeline.py` are **empty tuples**, yet `downstream_consumers()`
still branches on `run_meta.selected_flow`. Delete the dead branches; do **not** teach the solver to
model flows that no longer exist.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| `when` predicate language grows into a DSL | Hard cap at `{key: value}` against run_meta; no expressions. Escalate to a stage body, never the predicate |
| Hollow contracts hide *conditional* deps; solver halts on legitimately-absent soft inputs | Soft inputs never gate admissibility — hard inputs only |
| Guardrail mass encodes real lessons that look like cruft | Phase 2 shadow disagreements surface each one before any deletion; deletions cite their replacement |
| Legitimate iteration (recut → remaster) mistaken for thrash | Explicit fixpoint loops with a declared convergence metric (§2.2) |
| Solver correct but slower to ship a master | Replay harness (§6.3) + one A/B full-auto against 0.1.0 on the same tape |
| Contract population silently changes 0.1.0 heal routing via `requires` edges | `MUX_CONTRACT_REQUIRES=0` default (§3.4); per-group flip only after shadow agreement |
| Five phase-orphan stages skipped by a phase-keyed plan — exactly the i13–i15 battleground | P0 todo: adopt them into `phases.py` before any group starts (§3.1) |
| `build_graph()` `lru_cache` serves stale contracts inside tests | Cache-clear fixture in every contract test |
| **D2:** precision invalidation under-invalidates → stale audio ships in `master.wav` | Per-stage activation gated on conformance-green; `AUDIO_MUTATING` last; `verify_master` epoch assertion as the loud backstop (§5.4) |
| **D1:** advance-past yields a complete-looking but hollow master | `defect_ledger.json` is a publishability input; PMQ refuses `publish_allowed` on any open ship-bar-degrading defect (§5.5) |
| **D1:** `ship_reachable` false-negative halts a healthy run | Unknown ⇒ reachable; only a *proven* unreachable path halts; ships as an always-reachable stub first (§5.6) |
| **D3:** default behaviour shifts per commit while §5 lands | Each §5.6 step independently shippable + green `pytest tests/`; ledger excess tracked per step against the §10.1 table |
| No-delta guard refuses a legitimate iteration loop | Convergence-metric contracts (§2.2); `no_delta` routes to reachability, never to an error |

**Corrections (implemented) to three mitigations above.**

- **"`MUX_CONTRACT_REQUIRES=0` default" does not mitigate that risk.** The flag gates `requires`
  edges only; `dispatch_delta.hard_input_paths` and `artifact_lifecycle.run_phase_checks` read
  contract `inputs` outside the graph and ignore it (§3.4). The real mitigations are the
  union-with-`FALLBACK_HARD_INPUTS` monotonicity rule and the four-basis hard/soft test (§4.3).
- **The D2 mitigation was one-sided and unsound.** "Per-stage activation gated on conformance-green"
  must be **two-sided** (source *and* consumer) with the result **clamped to a subsequence of the
  blanket set**; the one-sided version dropped four real consumers of
  `transcript/protected_zones.json`, and the unclamped version doubled `audio_probe_build`'s blast
  radius from 30 to 60 (§5.4).
- **New risk, realised once already.** Applying a blanket "conditionally present ⇒ soft" rule
  dropped `transcript/full.json` from three stages' hard inputs, which would stop G0 corrections
  re-triggering them. Mitigation: the four-basis rule (§4.3), pinned by
  `tests/test_contract_input_declaration_safety.py`.

---

## 10. Verify

```bash
./tools/check_prerequisites.sh
pytest tests/
python tools/audit_config_keys.py
./scripts/verify_artifact_contract.sh
```

Plus new: `pytest tests/test_contract_conformance.py tests/test_contract_ownership_xcheck.py
tests/test_contract_tier_partition.py tests/test_path_ssot_drift.py
tests/test_solver_admissible.py tests/test_solver_posture.py`.

New ownership rows required for `operator/contract_observed.json` and
~~`operator/solver_shadow.jsonl`~~ **`operator/solver_decision.jsonl`** (mode `operational`; one
artifact, §6.2 correction) per
[artifact-ownership.md](../../docs/cross-cutting/artifact-ownership.md).

### 10.1 Success metric

The campaign is only worth running if this number moves. Baseline is `exec_11871`:

| Metric | Baseline | After 0.2.0 brain (measured) | Target |
|---|---|---|---|
| Excess dispatches, total | **235** | ~193 | < 15 |
| — conductor-issued | 42 | **0** (conductor removed) | 0 |
| — driver/rerun-issued | **193** | 193 | ~~**< 10**~~ **40–55** (§5.6 correction) |
| Worst-group thrash ratio (`build`) | **7.5×** | — | < 1.3× |
| Wall clock, same tape, full-auto | **11 h 47 m** | < 4 h |
| Code interventions needed to ship | **54** | 0 |
| Hollow contracts | ~~**45 / 90**~~ **48 / 91** (§1.1) | 0 |
| `authority_denied` / `seed order` runtime failures | 10 fingerprints | **0 seed-order leapfrogs under authority** (solver composes `_seed_prereq_block`; SEED_ORDER hard edges + `tools/audit_seed_contract_alignment.py`). Ownership denies remain separate. |
| Control-layer lines | ~12,900 | ~~< 2,000~~ **RETIRED by D13 — see §11** |

Measure excess with the same ledger arithmetic used in §3.2 so the numbers stay comparable.

**Correction (implemented) — three things about this table.**

1. **The `< 10` driver/rerun target is not reachable in this tree**; the measured expectation from
   the four P1.5 steps is 140–155 of 193 removed, because the no-delta guard runs on a weaker
   state-token witness wherever a stage declares no hard inputs. Full reasoning in §5.6. The
   "Excess dispatches, total < 15" row inherits the same error — it cannot hold while the driver
   row is 40–55.
2. **Attribution moved.** The ~49 M3 backward rewinds are **not** collected by §5.4 precision
   invalidation (which removes 3.0% of stage-slots and shrinks nothing for those seven stages).
   Credit them to §5.2 / §5.3 / §5.5 when scoring this table, or the same dispatches get counted
   against a step that never touched them.
3. **Every "after" figure here is still a prediction.** No run has been made since 0.2.0 landed
   (D9), so the "After 0.2.0 brain (measured)" column remains the `exec_11871` decomposition and
   nothing in the Target column has been observed. See the status section at the top.

### 10.2 Observability the solver owes the operator

When the admissible set is empty the run halts — so the halt message *is* the product. Emit
`operator/solver_decision.jsonl` per step with the chosen stage, and on halt the full unmet-`InputDep`
list with the producer that would satisfy each. The GUI needs a "why is nothing runnable" panel;
without it a structural halt is less debuggable than today's thrash, which at least kept moving.

**Correction (implemented):** this is the **same, single** artifact as §6.2's shadow log — that
section said `solver_shadow.jsonl`, which never existed. `operator/solver_decision.jsonl` carries
both the shadow comparison and the decision/halt payload. Landed, together with
`frontend/src/components/workspace/SolverHaltPanel.tsx` as the "why is nothing runnable" panel.

---

## 11. Phase 4 — the promotion path (operator decisions D10–D15, 2026-09-16)

Everything above is **built**. The replay harness then vetoed promotion (status section), and the
veto is not about correctness — the solver is nearly always right when it has an opinion. It is
about **coverage**: it has no opinion at 74.8% of decision points. This phase buys coverage.

The three gate failures decompose into exactly two work items plus a recalibration:

| Replay finding | Count | Cause | Owner |
|---|---|---|---|
| `hard_inputs_undeclared` | 4,956 unknowns | contracts populated but not enforced | **D11** — strict ratchet |
| `gate_auto_accept_pending` + `gate_may_pause` | 3,132 unknowns | gate state is not on disk | **D10** — persist gate decisions |
| authority 25.2% vs 80% | — | denominator assumed gates were solver-decidable | **D12** — replace the metric |

### D10 — gate state becomes on-disk fact

**Chosen:** record gate resolutions to `mastering/homunculus/gate_decisions.json` so `_gate_verdict`
reads a fact instead of guessing. Rejected: optimistic auto-clear (asserts the unprovable),
excluding gates from solver scope, and simply relaxing the 5% bar.

**The finding that makes this small.** `set_gate_decision` (`homunculus/gates.py`) has exactly **one**
production caller in the entire tree: the `set_gate` tool dispatch at `homunculus/loop.py:239`. That
is the **LLM conductor tool loop**, which brain 0.2.0 removed. So under the current default brain
**no gate decision is ever recorded** — `gate_decisions.json` is written only by the plane that no
longer runs, and the solver's 2,486 `gate_auto_accept_pending` deferrals are the direct consequence.

> This is a **second instance of the §5.0 strand-bug pattern** — a predicate written for the LLM
> plane that 0.2.0 inherited and that can never fire. §5.0 predicted "look for this shape wherever
> 0.2.0 inherited a predicate written for the LLM plane"; this is that shape, found. Audit the rest
> of the `set_gate`-adjacent tool surface for more of them before building.

Work:

1. Record the resolution at the point the deterministic plane **acts on** a gate — auto-accept in
   full-auto, and the pause/resume decision for `PARTIAL_MAY_PAUSE_GATES` — reusing
   `set_gate_decision` so the ledger row and the validation rules in it still fire. Do **not** add a
   parallel writer; the artifact already has its ALLOW row (`artifact_ownership.py:877`).
2. `_gate_verdict` (`solver.py:477`) consumes the recorded decision: a resolved gate is clear or
   blocked, never `unknown`. Keep `gate_indeterminate` for genuinely absent state.
3. Preserve the §8.1 correction — `audio_preclean` **self-skips** and must stay dispatchable; this
   work must not turn a recorded preclean decision into a blocking gate term.
4. Preserve the §8.2 parity requirement: any gate-state change needs
   `frontend/src/utils/partialOperatorGates.ts` updated in the same change.

**Done when:** structural deferrals fall from 26.3% toward the `gate_indeterminate` floor, and a
test proves a full-auto run records a decision for every gate it passes.

### D11 — strict ratchet, payoff-first

**Chosen:** flip `STRICT_GROUPS` (`contract_conformance.py:45`, today `("prepare",)`) in payoff
order — **`build` first**, then `understand-a/b/c`, then `fill_gaps` / `plan_rank` / `sound` / `ship`.

**This deliberately overrides §3.3's upstream-first rule, and the reason it is safe is specific:**
§3.3 requires upstream-first because *declaring* a stage's `inputs.hard` before its producers declare
`outputs` mints phantom blockers. **Population already happened repo-wide** — every group is
populated and report-only (status section), and hollow contracts are down from 48/91 to **15/90**, of
which only ~4 (`podcast_publish`, `selection_framing_apply`, `gap_framing_recompose`,
`mastering_research_routing`) are pipeline stages. So what remains is an **enforcement** order, not a
declaration order, and §3.3's hazard is largely spent. `build` leads because it is the worst group
(7.5× thrash, 71 of 227 excess).

**Residual risk to watch, since it is not zero:** flipping `build` strict while its upstream is
report-only means `build`'s conformance failures get attributed to producers nobody is enforcing
yet. If that noise dominates, fall back to §3.3 order for the remainder rather than fighting it.
Per-group rollback is `MUX_CONTRACT_STRICT_GROUPS` (§8.10); the constant only ever grows.

**Done when:** each flipped group meets the four-item Phase 1 bar (§3.5 as corrected), and the
replay's `hard_inputs_undeclared` count drops measurably per flip.

### D12 — replace the authority percentage gate

**Chosen:** drop the "80% of decision points" condition. Promotion requires:

1. **Zero unexplained disagreements** on replay (today: 1 of 14; the other 13 are mtime-reconstruction
   artifacts and stay excluded), and
2. **No regression against the driver** — for every replayed decision point the solver must not
   propose a stage the driver's own history proves was not runnable.

Rationale: an authority percentage is the wrong shape for a gate, because a solver that defers is
*safe* — deferral falls back to the driver. The thing that must be zero is being confidently
**wrong**. Keep publishing the coverage number in the report as the progress signal for D10/D11; it
just stops being a veto. `structural_deferral_bounded` likewise becomes a reported metric, not a gate.

**Note:** `tools/solver_replay.py` implements the current three gates and must be updated with this
decision, or the report will keep vetoing on a bar this plan no longer holds.

### D13 — subtraction: retire the target, authorise the top of §12 only

**Chosen:** the ~12–16k-line / `< 2,000` control-layer target is **RETIRED** (struck in §10.1). It was
never reachable without rewriting call sites; `p3-subtract` is **closed** at 427 gross / 406 net, and
the no-rewrite deletable set is genuinely **exhausted** (0 symbols / 0 lines).

Authorised: the **2–3 modules with the smallest caller-file blast radius** from §12.3 of
[subtraction-holes.md](../../docs/cross-cutting/subtraction-holes.md) — sequence by `caller files`,
not by line count. The remaining EXTERNAL set (256 symbols / 8,710 lines / 12 modules) stays
**unauthorised**.

**The §12.2 hazard governs this work and is not optional.** These call sites use function-local
imports inside broad `except Exception: pass`, so deleting a symbol raises and is swallowed: **the
guard silently stops guarding and the suite stays green.** Therefore each deletion needs *positive*
evidence — a test that fails when the replacing contract rule is removed. A green suite is not
evidence. D7's citation waiver does **not** extend here; these deletions cite their replacement.
D8 still holds: pinned forensics tests are never deleted and may fail as the hole map.

### D14 — validation sequencing

**Chosen:** replay stays the instrument. A live full-auto is a **post-forensics** confirmation, run
after the D12 gate is met, not a precondition for meeting it. D9 stands unchanged while the
forensics campaign is open, and `MUX_SOLVER_AUTHORITATIVE` does not flip on replay evidence alone —
it flips on the D12 gate, and the live run confirms.

### D15 — plan vehicle

**Chosen:** this plan is extended in place rather than superseded. §1–§10 are the record of what
shipped and the corrections that came out of shipping it; §11 is the remaining work. Two stale todos
were corrected with it: `p3-subtract` (was `pending`, is **closed**) and `p3-capability-predicates`
(was `in_progress`, is **done** — `has_dispatch_ledger` / `llm_owns_control_flow` are live across six
modules, one `is_homunculus_run` site left in `runtime.py`).

### 11.1 Order of work

D10 and D11 are independent and can run in parallel; both feed the same replay report.

1. **D10** — audit the `set_gate`-adjacent tool surface for sibling strand bugs, then record gate
   decisions from the deterministic plane and teach `_gate_verdict` to read them.
2. **D11** — flip `build` strict; measure; then `understand-a/b/c`; then the rest.
3. **D12** — update `tools/solver_replay.py` to the new gate, re-run, and read the coverage numbers
   as progress rather than as a veto.
4. **D13** — the two or three lowest-blast-radius EXTERNAL modules, each with a
   rule-fires test.
5. **Promotion** — flip `MUX_SOLVER_AUTHORITATIVE` when the D12 gate is met; live full-auto confirms
   once the forensics campaign closes (D14).

### 11.2 Verify

```bash
pytest tests/test_solver_replay.py tests/test_solver_posture.py tests/test_solver_admissible.py \
       tests/test_contract_conformance.py tests/test_v2_phases_mirror.py
python tools/solver_replay.py          # regenerates solver-replay-validation.md
```

Plus the standard §10 block, and `./scripts/build_gui.sh` if `partialOperatorGates.ts` changes.
