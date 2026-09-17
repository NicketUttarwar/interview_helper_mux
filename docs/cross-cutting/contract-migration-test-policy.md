# Contract-migration test policy — what may be deleted, and what may never be

The contract-authoritative migration (`.cursor/plans/solver_brain_020.plan.md`) ends in
**subtraction**: ~13k lines of imperative guardrails in `thrash_hardening.py`,
`delivery_guardrails.py`, `homunculus/agenda.py`, `recovery_controller.py` and
`stage_completion.py` are replaced by declarative contract rules. That subtraction will break
tests, and there are **4,182 tests across 538 files** to break. This doc is the policy from plan
§8.8, written **before** any deletion.

> Making a build green by deleting the forensics corpus is the single worst outcome available
> here. A red pinned test means the replacement is wrong, not that the test is stale.

---

## The two buckets

Every deleted test is classified as exactly one of the following.

### 1. Pinned lessons — never delete

These encode **invariants** discovered by paying for them in an 11h47m full-auto run. They do not
assert an implementation; they assert that a class of failure cannot recur. If one fails under the
contract solver, **the solver is wrong**.

| Corpus | How to recognize it | Count at time of writing |
|---|---|---|
| Forensics cascade fixtures from interventions **i1–i54** | `tests/test_i*.py`, plus any test that sets `MUX_FORENSICS=0` | 91 files set `MUX_FORENSICS` |
| Predicate families **F1–F7** (closed campaign ledger) | `tests/test_f[0-9]*.py` — see [predicate-families.md](./predicate-families.md) | 8 files |
| Predicate families **H\*** (HEAD identify ledger) | `tests/test_h??[0-9]*.py` — see [predicate-families-head.md](./predicate-families-head.md) | 55 files |
| Predicate families **End-A…F** (mastering/delivery seal) | `tests/test_end[a-f]*.py` — see [predicate-families-endgame.md](./predicate-families-endgame.md) | 6 files |

Union: **99 files**. A family ledger row names its fixture in its *Fixture / test* column; a test
named there is pinned by definition, whatever its filename.

**Also pinned:** the P0 precondition tests for this migration, because the plan's own soundness
depends on them — `tests/test_phase_partition.py`, `tests/test_contract_tier_partition.py`,
`tests/test_path_ssot_drift.py`.

If a pinned test asserts an invariant through a mechanism the solver removes, **rewrite the
mechanism, keep the assertion**: same test name, same ledger row, new plumbing. Do not delete and
re-add under a new name — the ledger row's citation must stay resolvable.

### 2. Scaffolding — may be deleted with the code it asserts

A test is scaffolding when it pins **how** the pipeline recovers rather than **what** must be true
of the result. Typical shapes:

- asserts a specific **heal route** (stage X repairs via stage Y) that a contract's
  `remediation` / `requires` edge now decides;
- asserts a **producer-pin table** entry (`PRODUCER_PIN_TABLE` in `stage_completion.py`,
  `_PROPAGATION_SEEDS` in `artifact_dependency_graph.py`) whose content moves into contract
  `propagation` / `consumers`;
- asserts a **retry / cycle count** (`max_mix_cycles`, `max_invokes_per_identity`,
  `max_conductor_turns`) that the no-delta dispatch guard replaces with a fixpoint rule;
- asserts the **thrash-hardening branch** that fires when the planner attempted something the
  solver makes statically inadmissible.

Deleting scaffolding is expected and healthy — it is the payoff for making contracts true.

### Tie-breaker

If a test could plausibly be either, it is **pinned**. Ask: *if this assertion never ran again,
could the failure it describes ship a master?* If yes, it is a lesson, not scaffolding.

---

## Rule for PRs

**Any PR that deletes or renames a test must classify every removed test in its commit message**,
one line each:

```
tests: drop mix-cycle cap assertions superseded by the no-delta guard

DELETED TESTS
- tests/test_thrash_mix_cycles.py::test_mix_stops_at_three  — SCAFFOLDING
  (retry count; replaced by dispatch_delta.no_delta refusal, §5.2)
- tests/test_agenda_heal_route.py::test_edl_heals_via_selection — SCAFFOLDING
  (heal route; replaced by edl.yaml inputs.hard[producer=full_master_ranking])
```

Requirements:

1. Every line is `PINNED` or `SCAFFOLDING`. There is no third option and no blank.
2. A `SCAFFOLDING` line names **the contract rule that replaces it** — the same citation rule the
   plan already imposes on code deletion (§7 step 4).
3. A `PINNED` line is only legal for a **rewrite** (test kept, mechanism changed) and must name the
   ledger row it belongs to. A PR that deletes a `PINNED` test outright is rejected.
4. Renames count as deletions: the ledger citation breaks otherwise.

Deletion follows the group order of plan §3.3 — **downstream-first** (`build` → `ship` →
`plan_rank` → …) and only **after** the solver is authoritative for that group. Never interleave
deletion with contract population.
