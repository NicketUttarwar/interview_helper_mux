# Subtraction holes — the `p3-subtract` worklist

**Status: CLOSED.** **427 gross lines removed / 21 shim lines added / 406 net**, across eight
guardrail files, reproducible from one `git diff --numstat 750f112c a31c0f81` **scoped to those eight
paths — copy the exact command from §1.4.6, because the scoping is not optional: the unscoped
`-- src/interview_mux/` form gives −489 / +1,248, since it also captures the solver 0.2.0 rewrite,
and −489 is not a campaign figure.** Those two figures are **authoritative** — quote them, together,
and never gross alone. **19 symbols** is authoritative too. The narrower "lines of guardrail *logic*"
figure of ~410 is **approximate and should not be quoted as precise**: it depends on a blank-line
counting rule this document does not define (§1.4.6). **The earlier totals 78, 421 and 393 are
retracted** (§1.4.6a). Every wave passed its attribution gate. The
no-rewrite deletable set is **exhausted** (`DELETABLE: 0 symbols / 0 lines`), not abandoned: what
remains is 8,710 lines that cannot be deleted without rewriting their callers, scoped as a successor
refactor in **§12**. Final accounting in **§1.4.6**.

**The final wave ran, and declined.** It attempted the two top-of-stack imperative control modules —
`seed_policy.py` (104L) and `recovery_controller.py` (1,816L) — and refused both, shipping **353
lines of pinning tests and zero deletions** (`3dd0ebf4`, §6.06). Nothing was skipped and nothing is
still open; the totals above are unchanged because nothing was deleted. The two rules that decided it
are in **§0** and apply to every future wave.

This document is the plan, the inventory, the execution record, and the worklist for the later
patching pass.

This is the execution record for `p3-subtract` in
[.cursor/plans/solver_brain_020.plan.md](../../.cursor/plans/solver_brain_020.plan.md) §7 step 4 —
deleting the imperative guardrail mass now that contracts, the dispatch door and the solver exist.

> **Operator waiver, in effect for this campaign.** The plan requires that *every deletion cites the
> contract rule that replaces it*. That requirement is **WAIVED**. Deletions proceed even where no
> replacement can be cited. A later pass patches the resulting holes. This document is the map that
> makes that later pass possible — which is why the "no proven replacement" rows in §6 are the real
> product, not a defect report.

---

## 0. What counts as a replacement — two rules, read before any wave

The most reusable output of the campaign. Both were bought with a wave that deleted nothing (§6.06),
and both would have prevented it. Apply them to a row's *Replacement* column **before** planning a
deletion around it: a row that fails either rule reads **nothing**, not "partial".

1. **Off by default is not a replacement.** Any replacement gated by `MUX_CONTRACT_REQUIRES`
   or `MUX_SHIP_REACHABILITY_HALT` is **nothing** until the flag defaults
   on. Both are off at HEAD — `artifact_dependency_graph.py` ("with the flag OFF, the default",
   emitting only the frozen baseline edge set),
   `ship_reachability.py:261` ("default OFF: the analysis always runs, the halt is opt-in"). A gated
   rule does not guard a run nobody set the flag for. **Rows mis-stated this and are now
   corrected: H-02, H-08, H-09.** Replacements that *are* on by default keep their "partial":
   `MUX_DISPATCH_NO_DELTA` and `MUX_DISPATCH_MEMO` (`dispatch_delta.py:113`–`118`, `default=True`),
   ownership fail-closed (`artifact_ownership.py:57`), the `master_epoch` seal assertion (§8.1) and
   precision invalidation (§12.4).
2. **A uniform contract declaration is not a replacement for a discriminating one. Check
   *cardinality*, not presence.** Contract `remediation` is present in all 91 contracts and declares
   `[volley_retry, full_stage_rerun]` in every one of them — no discrimination among the 37 error
   classes `recovery_controller` names, and no resume stage. 91 identical blocks carry **zero bits**
   about which failure shape occurred. A populated field proves a schema, not a behaviour.

---

## 1. Recovery point — read this before touching anything

Mass deletion runs against a working tree holding uncommitted forensics-campaign work. Two
snapshots exist. Both were minted **without modifying the working tree or the index**.

| Tag | SHA | Covers |
|---|---|---|
| `pre-subtraction-snapshot` | `1f4692b7bca408e47b6ddd78a3b2f0d87c06b2af` | Tracked modifications only (`git stash create`) — 8,883 files vs HEAD |
| `pre-subtraction-snapshot-full` | `00af3f3ef5ddc30fe5dfd16c036bd37748f3119e` | Tracked + untracked — 10,145 files vs HEAD |
| **`pre-subtraction-snapshot-full-w0`** | **`750f112c7be02d07e69fe5028c61a8f2bf8963c3`** | **Re-mint immediately before W0 — 10,169 files vs HEAD. This is the W0 rollback.** |

**Use `pre-subtraction-snapshot-full` for rollback.** `git stash create` does **not** capture
untracked files, and the entire new contract/solver system is currently untracked — `solver.py`,
`dispatch_door.py`, `ship_reachability.py`, `artifact_ownership.py`, `contract_conformance.py`,
`defect_ledger.py`, `master_epoch.py`, `dispatch_delta.py`, and ~40 new test files. The tracked-only
snapshot would restore the guardrails and lose the replacement. The full snapshot was built with a
temporary `GIT_INDEX_FILE` (`git read-tree` + `git add -A` + `commit-tree`), which writes only to a
scratch index and never touches the real index or the working tree. Presence of all eight new
modules inside the tag was verified with `git cat-file`.

Both tags are real refs, so the dangling commits cannot be garbage-collected.

### 1.1 Proof the working tree was not modified

`git diff` over all tracked files hashed identically before and after both snapshot operations
(`16b11dba…`), and `git diff --cached` stayed empty (`e3b0c442…`, the hash of nothing). The only
delta in `git status --porcelain` across the whole operation was **two new untracked test files**
appearing — `tests/test_prestage_hard_input_refusal.py` and `tests/test_solver_shadow.py` — created
by the concurrently-running workers, not by this work. No file was modified, staged or removed.

### 1.2 Re-mint before every wave — hard requirement

The tree is edited by other workers continuously, so a tag is a snapshot of *its own moment*, not of
the moment a wave starts. **Every wave re-mints its own `pre-subtraction-snapshot-full-<wave>` by
the temp-index method immediately before deleting**, and rolls back to that one.

Two practical notes from the W0 re-mint:

- `git add -A` into the scratch index **races the GUI build**. The first attempt aborted with
  `unable to stat src/interview_mux/web/static/assets/…js` because a worker rebuilt the bundle
  mid-scan. Re-minting needs a retry loop; a single attempt is not reliable on a live tree.
- Snapshots age within minutes. `tests/test_solver_shadow.py` landed between the first snapshot and
  the second and was absent from the first.

### 1.3 Forbidden commands, for the whole campaign

`git stash` (bare), `git stash push`, `git checkout --`, `git restore`, `git reset`, `git clean`.
Rollback is `git checkout <tag> -- <specific paths>`, never a tree-wide reset.

---

## 1.4 W0 execution record — the calibration wave

**Executed. Gate passed.** W0 deleted **343 lines / 12 functions** across six modules, as a pure
deletion (zero added lines, verified by diffing the six files against
`pre-subtraction-snapshot-full-w0`). That 343 is the `git diff` count; the same 12 symbols measure
**~332** by AST, the difference being blank lines — a distinction that depends on the undefined
counting rule in §1.4.6c, so treat 332 as approximate and 12 symbols as the firm figure. Summing 343
with the AST-counted later waves is what produced the retracted 421 — see §1.4.6a.

| | |
|---|---|
| Baseline run 1 | 205 failed / 4,341 passed |
| Baseline run 2 | 204 failed / 4,343 passed |
| Flaky node ids (excluded from both sides) | 1 |
| Stable baseline | **204** |
| After W0 | **204** |
| **NEW failures** | **0** |
| **PREDICTED failing test files** | **0** |
| **UNEXPLAINED (`NEW \ PREDICTED`)** | **0** — gate passed |

Deleted: `artifact_completeness.complete_manifest_from_boundaries`, `.attach_gap_fill_to_input`;
`delivery_guardrails.delivery_epoch_matches`, `.read_delivery_epoch_at_dispatch`;
`identical_failures.record_failure_unified`, `.halted_rows`;
`remediation_framework.honest_playbook_outcome`;
`stage_resilience.before_mark_done`, `.reconcile_stage_if_stale`;
`thrash_hardening.maybe_sticky_halt_on_true_waste`, `.clear_sticky_heal`, `.classify_gate_wait`.

**Verified still in force at campaign close.** All twelve have zero definitions anywhere in
`src/interview_mux`.

**Known cosmetic leftover — one stale docstring, not yet tidied.**
`src/interview_mux/identical_failures.py:6` still names `record_failure_unified`, which W0 deleted.
It is a prose mention in a module docstring, so it changes no behaviour and no test. It is recorded
here rather than fixed because this pass was documentation-only and that is a source file. Whoever
next edits `identical_failures.py` should drop the reference. It is the only surviving trace of any
W0 symbol.

### 1.4.1 What calibration caught — the reason W0 exists

The harness was wrong twice before it was right, and both errors would have been catastrophic if
they had first surfaced on W2's 51% of the mass.

1. **Intra-module references were not counted.** The first scan looked only for references *outside*
   the defining module, and so reported `stage_acceptance.AcceptanceResult` as dead code. It is the
   return type of `stage_acceptance_ok` — the runtime acceptance contract, and per §3 a keep-whole
   module. Deleting it would have taken out the sufficiency engine on the wave advertised as
   "provably zero blast radius". It also wrongly reported all 23 `recovery_controller.playbook_*`
   functions as dead; they are reached through an in-module dispatch table.
2. **`tools/` was not scanned.** `tools/full_auto_driver.py` — the full-auto forensics campaign
   driver — contains live calls to `artifact_repairs.realign_manifest_roles_from_speakers`,
   `delivery_guardrails.generate_missing_referenced_music_assets`,
   `forensics_stall.sync_escalation_with_product` and `thrash_hardening.stable_fail_key`. Deleting
   those four would have broken the active campaign driver while leaving `pytest` green — a silent
   break of exactly the kind this document exists to prevent.

**Net effect: the W0 candidate set fell from 1,516 lines to 343 — the first estimate was 4.4×
over-broad.** Any line-count projection in this document that predates `tools/subtraction_predict.py`
should be treated as an upper bound, including the §2 totals.

### 1.4.2 Cascade — W0.1

Deleting `attach_gap_fill_to_input` orphaned its only callee,
`artifact_completeness.build_gap_fill_context` (62L). It was **not** deleted: a wave's deletion set
is fixed by its pre-wave scan, and deleting cascades mid-wave breaks the predicted-set discipline.
It is the first entry of the next wave. Every wave should expect a cascade tail and re-run
`orphans` afterward.

### 1.4.2a W2c precondition re-check (post-`correctness: true` markers)

Re-evaluated directly rather than inferred, after `correctness: true` was added to `mix`,
`master_finalize`, `junction_snip_qa` and `edl`:

```
critical_path() → 2 requirements
  ingest/normalized.wav   (ingest)        → required_by mix
  master/assembly.wav     (mix)           → required_by master_finalize
root_producers: ('master_finalize',)      unknown_stages: ('ingest',)
selection chain stages on critical path: NONE
```

The markers did **not** put the selection chain on the critical path. `full_master_ranking`,
`selection_framing_apply`, `selection_order_sanitize`, `edl`, `transitions`, `junction_snip_qa` and
`air_script_compose` are all absent. The PMQ fail-open is closed, but that is only one of the two
preconditions. **W2c remains BLOCKED.**

### 1.4.3 Batch 1 — the closure defect, and the real size of the campaign

Batch 1 (the `ship` + `build` + `plan_rank` Class A merge) was **deleted, failed its gate, reverted,
re-planned, and re-deleted.** The failure is worth recording because it is the same class of error
as §1.4.1 and it got past a tool that was supposed to prevent it.

The `plan` subcommand added for the live-tree pass classified a symbol as `DELETABLE` when nothing
*outside* its module referenced it. It never asked whether a **sibling symbol in the same module**
called it. Forty-nine functions were deleted out from under their in-module callers, producing 126
new failures across 36 files against a 7-file predicted set — **76 unexplained, gate violated.**
`orphans` had been hardened against exactly this in §1.4.1; the new command reintroduced it.

The fix is a fixpoint, not a per-symbol test: *a symbol is deletable only if every sibling caller is
also being deleted.* Iterate evictions until stable. Running it evicted **187 symbols / 3,416 lines**
that had looked self-contained.

**Consequence for the campaign's size — see §1.4.6 for the final figure.** The §2 and §9 totals are
module-level upper bounds that assume call sites are rewritten. The *no-rewrite* deletable set —
symbols that can simply be removed — is smaller by orders of magnitude, and each successive
correction to the planner shrank it further.

### 1.4.4 References *between* candidate modules are not free either

The per-module closure in §1.4.3 was still not enough. The planner computed
`external = other_src_files - owned - candidate_files`, which **discounts references coming from
other candidate modules** on the theory that those files are being edited anyway. They are not: only
the *deleted symbols* go away, and every surviving symbol in those files keeps its call sites.

`heal_routing.resume_stage_for_error_class` was deleted this way while
`stage_completion.incompleteness_resume_stage`, `delivery_guardrails.safe_mix_resume_stage` and
`recovery_controller.handle_stage_failure` still called it — through **function-local imports**, which
is why a file-level scan attributed them to the candidate set and dismissed them.

This failure mode is worse than a `NameError`, and the reason is the shims. These call sites sit
inside `except Exception: pass`. A missing symbol therefore does not crash — **the guard silently
stops guarding, and the suite stays green where it matters.** A raising shim converts a loud
`ImportError` into exactly the silent hole this campaign exists to find.

The closure must therefore run over **every top-level symbol in `src/`**, treating a reference as
discharged only when the referencing symbol is itself in the delete set. That is what
`_closure_evict` now does, and the per-symbol and per-module views are both retired.

### 1.4.5 Collection errors abort the entire suite

A single `ImportError` in one test file makes pytest exit with
`Interrupted: N errors during collection` and **run nothing at all**. Batch 1 hit this: the first
after-run reported "1 error in 3.46s" and the gate read it as a near-perfect result, because a suite
that never ran has almost no failures. That is a false pass, and it would have been a silent one.

Two consequences, both now standing practice:

- **Gate on `pytest --collect-only` (~3 s) before spending ~5 min on a suite run.** It catches the
  whole class for 1% of the cost.
- **The shim ruling is not a nicety, it is what makes attribution possible.** Deleted symbols that
  any test imports get a raising stub with a pointer to this document. The pinned test then fails on
  its own assertion — a readable hole — instead of destroying the run. Batch 1's **first attempt**
  needed eleven shims across five modules — and that attempt was **reverted**. The batch as shipped
  carries **three** shims in two modules; inventory in §1.4.6b.

### 1.4.6 Final accounting — the campaign is CLOSED

Run on a quiet tree with every carve applied **before** the closure, `subtraction_predict.py plan`
returns the four-bucket partition of the whole seed list:

| Bucket | Symbols | Lines | Disposition |
|---|---:|---:|---|
| LOAD_BEARING — the new system depends on it | 22 | 833 | never deletable |
| CARVED — Class B, silent wrong master | 266 | 11,544 | deliberately out of scope (§9.2) |
| EXTERNAL — deletable only by rewriting callers | 256 | 8,710 | **successor work item — §12** |
| DELETABLE — no-rewrite | **0** | **0** | exhausted |

**Shipped by this campaign: 427 gross lines removed, 21 shim lines added, 406 net.** Publish those
two numbers **together** — "427 gross / 406 net". Quoting gross alone is what invited repeated
re-derivation (§1.4.6a).

**Read the figures in two tiers, and do not mix them.**

| Tier | Figure | Basis |
|---|---|---|
| **AUTHORITATIVE — quote these** | **427 gross removed / 21 added / 406 net**, and **19 symbols** | falls straight out of the one scoped command below, with no interpretation; anyone reproduces it exactly |
| **APPROXIMATE — do not quote as precise** | ~410 lines of guardrail *logic* | requires a rule for which blank lines "belong to" a deleted symbol, and **no such rule is defined** (§1.4.6c) |

The measurement is one command against the pre-W0 baseline tag (`750f112c`) through the campaign's
current commit (`a31c0f81`):

```
git diff --numstat 750f112c a31c0f81 -- \
  src/interview_mux/thrash_hardening.py src/interview_mux/artifact_completeness.py \
  src/interview_mux/identical_failures.py src/interview_mux/remediation_framework.py \
  src/interview_mux/stage_resilience.py src/interview_mux/delivery_guardrails.py \
  src/interview_mux/heal_routing.py src/interview_mux/delivery_invariants.py
```

| Guardrail file | Gross removed | Shim lines added |
|---|---:|---:|
| `thrash_hardening.py` | 164 | 13 |
| `artifact_completeness.py` | 79 | 0 |
| `identical_failures.py` | 78 | 0 |
| `remediation_framework.py` | 39 | 0 |
| `stage_resilience.py` | 31 | 0 |
| `delivery_guardrails.py` | 23 | 0 |
| `heal_routing.py` | 8 | 8 |
| `delivery_invariants.py` | 5 | 0 |
| **Total** | **427** | **21** |

**Eight files, and that is the whole scope.** Only two of them gained a line — the shims live in
`thrash_hardening.py` and `heal_routing.py`; the other six are pure deletions. No ninth file belongs
in this count; §1.4.6a covers the two that were wrongly included once.

**The scope proof is the symbol count, not any line count.** The eight files hold **19** deleted
symbols, and 19 splits exactly W0 12 + batch 1 6 + closeout 1 — the same per-wave symbol counts this
document recorded independently, wave by wave, as each wave passed its gate. That is a symbol-count
match, it is unaffected by any blank-line convention, and it is what confirms the eight-file set is
the complete scope.

| Wave | Symbols | Symbol-body lines (approx., §1.4.6c) | Gate |
|---|---:|---:|---|
| W0 — calibration wave (§1.4) | 12 | ~332 | passed — reported at the time as 343 from `git diff` |
| Batch 1 — ship+build+plan_rank merge (§6.05) | 6 | ~75 | passed, 4 new failures all predicted |
| Closeout — `delivery_invariants._active_listen_delight_remutate_stages` | 1 | ~3 | passed, **zero** new failures |
| **Total** | **19** | **~410** | |

**The symbol column is authoritative; the line column is not** — see §1.4.6c before quoting it.

Of the 19, sixteen are gone outright (~355 lines) and three survive as raising shims whose old bodies
(~55 lines) are counted here as removed logic. **That 16 / 3 split and its line decomposition are
taken on trust from the campaign record and have not been re-verified independently** — only the three
shims themselves have been confirmed present on disk (§1.4.6b).

### 1.4.6a Retracted totals — 78, 421, 393

Three totals were published before the measurement above settled it. All three are **withdrawn**.
They are recorded here, with their causes, so that a reader who encounters one in an older note does
not re-derive yet another number.

- **78 — retracted.** Omitted the W0 wave entirely and counted only batch 1 plus closeout. Already
  withdrawn at the time.
- **421 — retracted; two incompatible rulers summed.** W0 was counted from `git diff` output, which
  includes blank separators, and reported **343**; its symbols measure **~332** by AST — an 11-line
  difference, under the same undefined blank-line convention flagged in §1.4.6c. Batch 1 (75) and the
  closeout (3) were counted by AST, with separator blanks
  excluded. 343 + 75 + 3 = 421 therefore mixes the two conventions. On a single consistent ruler the
  campaign is **427** (gross `git diff` removals — authoritative) or *approximately* 410 (AST symbol
  bodies, and only as precise as the blank-line rule behind it, §1.4.6c) — never 421.
- **393 — retracted; two errors that masked each other.** It omitted `artifact_completeness.py`
  altogether (79 gross, a pure deletion), and it wrongly included `ship_reachability.py` (−33) and
  `defect_ledger.py` (−12). Those two are **solver 0.2.0 rewrites**, not guardrail subtraction: they
  gained +264 and +451 lines respectively in the same commit, and their deletions are refactor churn
  (`_contract_requirements`, `degrades_ship_bar`, `defects`, and a batch of `except Exception:`
  lines). The arithmetic closes exactly: 427 − 79 + 45 = 393.

**Running count: five figures have been attempted for one campaign — 78, 421, 393, the 410-versus-392
pair, and the authoritative 427 gross / 406 net.** The root cause of all five is the same, and it is
worth stating once, plainly: **these were not arithmetic errors. They were undeclared changes of
measuring convention.** Every figure was arithmetically correct on its own ruler; what went wrong
each time was summing across rulers, or changing rulers without saying so. The lesson is procedural:
**fix the ruler before summing, name it when publishing, and prefer the figure that needs no
interpretation** — which is why §1.4.6 now tiers the numbers by confidence instead of publishing a
single headline count.

### 1.4.6b Shim inventory — three, not eleven

Only **three** shims exist in the committed tree, and they account for all **21** added lines in the
table above: **13 lines of function body plus 8 non-body lines** — their comment banners and
separators. This is the one part of the decomposition confirmed directly on disk:

| Shim | Module | Old body |
|---|---|---:|
| `gate_wait_tick` | `thrash_hardening.py` | 27L |
| `wasted_work_is_true_waste` | `thrash_hardening.py` | 21L |
| `apply_heal_route` | `heal_routing.py` | 7L |

Each raises `NotImplementedError` with a pointer to this document, per the §1.4.5 ruling. **The
"eleven shims across five modules" figure describes batch 1's first attempt, which was reverted**
(§1.4.3); it never shipped and should not be quoted as the campaign's shim count.

### 1.4.6c Why ~410 is approximate — the blank-line rule is undefined

`427 − 17 = 410` was published on the basis that 17 blank separator lines travelled out with the
deleted functions. **A plain blank-line count over the removed lines of the eight files gives 35, not
17** — per file: `thrash_hardening` 6, `artifact_completeness` 9, `identical_failures` 4,
`remediation_framework` 3, `stage_resilience` 4, `delivery_guardrails` 5, `heal_routing` 2,
`delivery_invariants` 2. On that count the logic figure would be `427 − 35 = 392`.

Both counts are defensible and they measure different things. The 17 are blanks **between** symbols;
the other 18 are blanks **internal to the deleted function bodies**, which an AST span legitimately
includes as part of the symbol. So 410 and 392 differ by a judgment call — and **that judgment call is
not written down anywhere.**

Three consequences, and they are the point of this subsection:

1. **Do not quote ~410 as a precise figure.** It is a reasonable estimate of guardrail logic removed,
   and nothing more. `392` is **not** a campaign total either; neither number should be cited as *the*
   answer.
2. **Quote 427 gross / 406 net instead.** They need no convention, no AST, and no judgment — just the
   command in §1.4.6.
3. **If the logic figure ever has to be defended, define the counting rule first** — specifically,
   whether a blank line inside a function body counts as removed logic — then re-measure under it and
   publish the rule alongside the number. Re-measuring without declaring the rule will produce a sixth
   figure, for the same reason the first five happened (§1.4.6a).

The scope proof does **not** rest on any of this. It rests on the 19-symbol count (§1.4.6), which no
blank-line convention can move.

The closeout deletion gated clean on 4,693 tests collected before and after, with **zero new failures
by node-id set comparison** — not merely a lower failure count, but proof that no node which passed
before fails after.

W0 is the reason the 8,900-line projection survived as long as it did: it deleted real mass and
passed its gate, which read as confirmation that the estimate was sound. It was a *calibration* wave
by design — chosen for symbols with no reference anywhere — and its success did not generalise. Every
line after it had to survive the closure rules in §5.1a, and almost none did.

The projection travelled **8,900 → 2,200 → 440 → 3**, and every step down was a tooling correction
rather than a change of policy:

| Estimate | What it assumed | What corrected it |
|---:|---|---|
| ~8,900 | module-level totals, call sites rewritten | scope restated as *no-rewrite* deletions |
| ~2,200 | a symbol is deletable if nothing outside its module references it | per-module closure (§1.4.3) |
| ~440 | references between candidate modules are free | global closure (§1.4.4) |
| **3** | carve-outs can be applied after the closure | carve-before-closure (§5.1a corollary) |

Each correction found live callers the previous one had discounted. Two of the four were found only
because a gate failed loudly; the carve-before-closure bug was found by distrusting a result that
contradicted an earlier one.

**This is the finding, not a disappointing outcome. The imperative guardrail mass is
superseded-and-still-wired, not superseded-and-orphaned.** `p3-subtract` as scoped — *delete the
superseded mass* — cannot be completed by deletion, because there is almost nothing left that is
merely dead. What remains is a refactor, scoped in §12 and to be authorised on its own terms.

### 1.4.7 Attribution noise from concurrent workers

The single flaky node id was
`tests/test_solver_decision_log.py::test_api_exposes_the_decision_and_the_halt_payload` — a new test
belonging to an active worker, flaky because it was being edited during the run. This is direct
evidence that **attribution degrades while the tree is live.** W0 tolerated it because its predicted
set was empty; a wave with a large predicted set cannot distinguish worker churn from deletion
damage. Waves must run on a quiet tree.

---

## 2. Scope and totals

Measured against the working tree at snapshot time. **See §1.4.1: pre-tool figures are upper
bounds.**

| | Lines |
|---|---|
| Seed-list modules (operator's list + `artifact_sanitize/*`) | **28,520** |
| — of which **KEEP** (load-bearing for the replacement, §3) | **4,661** |
| — of which **DELETABLE** | **23,859** |
| Second-ring modules reached through the call graph (§7) | 5,309 |
| **Total deletable, both rings** | **~29,168** |

Against the plan's §10.1 target of "control-layer lines ~12,900 → < 2,000", this campaign is
larger than the plan projected because the plan's line-count table (§1.1) counted only five
modules. The real mass is spread across 17 seed modules plus 22 `artifact_sanitize` submodules.

### 2.1 Per-module breakdown

| Module | Total | KEEP | Deletable | Why the keep |
|---|---:|---:|---:|---|
| `artifact_repairs.py` | 6,268 | 890 | **5,378** | two repair fns called by `write_staging` |
| `artifact_sanitize/*` (22 files) | 4,390 | 0 | **4,390** | nothing in the new system imports it |
| `thrash_hardening.py` | 3,488 | 0 | **3,488** | nothing in the new system imports it |
| `delivery_guardrails.py` | 2,904 | 0 | **2,904** | nothing in the new system imports it |
| `recovery_controller.py` | 1,816 | 0 | **1,816** | nothing in the new system imports it |
| `execution_invalidation_profiles.py` | 715 | 0 | **715** | superseded by contract `propagation` |
| `stage_input_checks.py` | 1,082 | 377 | 705 | `require_stage_inputs` ← `write_staging` |
| `artifact_lifecycle.py` | 793 | 201 | 592 | commit/fingerprint hooks ← `write_staging` |
| `identical_failures.py` | 1,057 | 487 | 570 | `record_identical_failure` ← `artifact_ownership` |
| `artifact_completeness.py` | 1,014 | 463 | 551 | **sufficiency engine for solver + reachability** |
| `heal_routing.py` | 660 | 0 | 660 | superseded by contract `requires` edges |
| `stage_completion.py` | 2,289 | **1,756** | 533 | **producer-pin table ← `artifact_ownership`** |
| `delivery_invariants.py` | 574 | 42 | 532 | `committed_master_wav` ← `ship_reachability` |
| `remediation_framework.py` | 442 | 36 | 406 | `read_active_remediation_plan` ← `ship_reachability` |
| `stage_resilience.py` | 577 | 268 | 309 | three flush hooks ← `write_staging` |
| `forensics_stall.py` | 184 | 0 | 184 | one importer, zero pinned tests |
| `seed_policy.py` | 104 | 0 | 104 | superseded by seed-index ordering in solver |
| `stage_acceptance.py` | 163 | **141** | 22 | **runtime acceptance contract — keep whole** |

KEEP figures are the transitive private-helper closure of each load-bearing public symbol, plus 6%
module overhead (imports, constants, docstring) where the module survives at all.

---

## 3. DO NOT DELETE — load-bearing for the replacement

**This is the most important section in the document.** These look like guardrail mass and are not.
Each was found by reading the imports of `solver.py`, `dispatch_door.py`, `ship_reachability.py`,
`dispatch_delta.py`, `defect_ledger.py`, `contract_conformance.py`, `master_epoch.py`,
`artifact_ownership.py` and `write_staging.py` — i.e. the replacement calling into the thing it is
supposed to replace. Deleting any of these is not subtraction, it is self-harm.

| Symbol | Lines | Consumed by | Consequence of deleting |
|---|---:|---|---|
| `artifact_completeness.artifact_status_for_stage` | 33 | `solver.py:357`, `ship_reachability.py:288` | Solver sufficiency term and reachability satisfaction check both lose their only notion of "is this artifact good enough". Every stage becomes trivially admissible. |
| `artifact_completeness` `_gaps_*` rule table + `compute_gaps` + `_gap_rule_for` | ~430 | transitively, via the above | The status function is a thin shell over ~30 per-artifact gap rules. Deleting the table silently degrades `artifact_status_for_stage` to "file exists". **This is the subtlest trap in the campaign** — the public symbol survives while its meaning is gutted. |
| `stage_completion.producer_pin_for_token` | 76 | `artifact_ownership.py:1748` | The ownership SSOT — the foundation of the whole contract system — resolves producer identity through the producer-pin table. The plan's §4.3 calls this table a *source* for contract population and the test policy calls assertions on it scaffolding; **the table itself is load-bearing until ownership stops calling it.** Its KEEP closure is 1,756 of `stage_completion.py`'s 2,289 lines. |
| `identical_failures.record_identical_failure` | 17 | `artifact_ownership.py:1920` | Ownership denials stop being recorded; the defect ledger loses its main feed. |
| `delivery_invariants.committed_master_wav` | 2 | `ship_reachability.py:132` | `ship_reachable()` cannot tell whether the master exists. D1's halt/advance decision becomes undefined. |
| `remediation_framework.read_active_remediation_plan` | 10 | `ship_reachability.py:313` | Reachability cannot see an active remediation plan and will call a recoverable run unreachable, or vice versa. |
| `stage_acceptance.stage_acceptance_ok` + `AcceptanceResult` | 141 | runtime sufficiency engine host | Routes schema validation, deterministic lint, null-field policy, `sufficiency_engine.evaluate` and cross-artifact validation. This *is* the sufficiency engine the contract `sufficiency` field describes. **Keep the module whole** — only 22 of its 163 lines are not load-bearing, and deleting them is not worth the risk. |
| `artifact_lifecycle.post_commit_validate`, `apply_fingerprints_on_flush`, `restamp_committed_artifact` | 120 | `write_staging.py` | The staged→committed promotion path. §8.6 of the plan requires admissibility to read *committed* state only; these are what make "committed" mean anything. |
| `stage_resilience.validate_staged_before_flush`, `after_flush_resilience`, `record_resilience_event` | 113 | `write_staging.py` | Same promotion path. Deleting these lets malformed artifacts commit, which the solver will then treat as satisfied hard inputs. |
| `stage_input_checks.require_stage_inputs` | 25 | `write_staging.py` | The pre-write input assertion. Until contract `inputs.hard` is enforced at the door for all 72 stages, this is the only thing stopping a stage writing from missing inputs. |
| `artifact_repairs.repair_manifest_segments`, `sync_content_brief_topic_segment_ids` | 236 | `write_staging.py` | Called on the write path; not a heal route. |
| `artifact_completeness.hydrate_manifest_from_boundaries`, `merge_artifact`, `BINARY_ARTIFACT_SUFFIXES` | ~160 | `write_staging.py`, `stage_acceptance.py` | Write-path helpers, and the binary-artifact suffix set that stops `read_json` being called on `cover.jpg` (the exec_11871 cover re-billing bug). |

### 3.0 Reproducing this list

`python tools/subtraction_predict.py orphans` prints it, flagging any candidate symbol referenced
from a `KEEP_MODULES` file. Re-run it before every wave — the replacement is under active
development and this list grows.

One known false positive: the tool reports `identical_failures._empty_doc` and `._write` as consumed
by `defect_ledger.py`. They are not — `defect_ledger` defines its own private helpers with the same
generic names, and imports nothing from `identical_failures`. The tool matches on bare symbol names
rather than resolved imports, which over-reports in the *keep* direction. That is the safe direction
and is left as-is; verify with `rg 'from interview_mux.<module> import'` before acting on a
surprising entry.

### 3.1 The two structural traps

1. **`artifact_ownership.py` depends on two delete-candidates.** The contract system's own SSOT
   imports `stage_completion.producer_pin_for_token` and `identical_failures.record_identical_failure`.
   Any wave that touches those two modules must be sequenced *after* ownership stops calling them,
   or it takes down the replacement along with the thing replaced. Neither call is in the current
   plan's dependency picture.

2. **`ship_reachability.py` depends on three delete-candidates** — `delivery_invariants`,
   `remediation_framework`, `artifact_completeness`. D1 "advance while reachable" is the behaviour
   that makes deletion survivable at all; it must not be deleted out from under itself.

---

## 4. Wave plan — downstream-first

Ordered per the operator's instruction: `ship` → `build` → `sound` → `plan_rank` → `fill_gaps` →
`understand-c` → `understand-b` → `understand-a` → `prepare`.

> **Deviation noted.** Plan §3.3 and the test policy both specify `build` → `ship` → `plan_rank` → …
> The operator's order puts `ship` first. Following the operator. The practical effect is small:
> `ship` is only ~5% of the mass, so it functions as a low-risk rehearsal wave before `build`, which
> is 51%. That is arguably the better order.

### 4.1 Phase attribution is approximate, and that matters

The guardrail modules are **not phase-separable**. Stage-id frequency analysis of each module:

| Module | build | plan_rank | other |
|---|---|---|---|
| `delivery_guardrails.py` | 68% | 12% | sound 8%, ship ~5% |
| `thrash_hardening.py` | 60% | 17% | ship 7% |
| `recovery_controller.py` | 62% | 19% | ship 7% |
| `artifact_repairs.py` | 25% | 37% | sound 12% |
| `stage_completion.py` | 27% | 33% | understand-c 10% |

Consequence: for these five, **waves cut at symbol level, not module level**. A module-level cut
would drag four phases' worth of breakage into one wave and destroy attribution. Phase-pure
modules (`stage_resilience` 100% build, `artifact_sanitize/selection.py` 100% plan_rank,
`artifact_sanitize/sound_design_plan.py` 100% sound) cut whole.

> **Superseded — historical.** §4 and §§8–10 were written before the closure rules in §5.1a existed,
> and their line estimates assume call sites get rewritten. Only W0 and the batch-1 merge ever ran;
> the rest were never authorised and are now moot, because the no-rewrite deletable set is exhausted
> (§1.4.6). **Read them as the original inventory and reasoning, not as a worklist.** The live
> worklist is §12. Per-wave figures here are the 4.4×-to-370× overestimates that §1.4.6 tracks.

### 4.2 The waves

| Wave | Phase | Deletable lines | Contents | Test blast radius (files / test fns) |
|---|---|---:|---|---|
| **W0** | none | ~1,516 | Pure dead code: 1,516 lines of public symbols with **zero** callers anywhere in `src/` or `tests/`. Includes all 23 orphan `recovery_controller.playbook_*` functions (307L), `thrash_hardening.maybe_sticky_halt_on_true_waste` (63L), `delivery_guardrails.resolve_music_limbo_exit` (123L), `artifact_repairs.repair_speakers` (177L), `stage_resilience.evaluate_stage_resilience` (98L). | **0 / 0** |
| **W1** | `ship` | ~1,120 | `forensics_stall.py` whole (184L, one importer, zero pinned tests); ship-attributed symbols in `delivery_guardrails` (publish/cover/podcast), `thrash_hardening`, `recovery_controller`, `delivery_invariants` (minus `committed_master_wav`). | ~12 / ~110 |
| **W2a** | `build` | ~1,700 | Phase-pure build modules: `stage_resilience.py` deletable (309L), `artifact_sanitize/edl.py` (147L), `vo_synthesize.py` (191L), `invalidate.py` (183L), `execution_invalidation_profiles.py` build share (~370L), `identical_failures` build share (~430L). | ~20 / ~180 |
| **W2b** | `build` | ~4,100 | `thrash_hardening.py` build share (~2,090L) + `heal_routing.py` build share (~356L) + `recovery_controller.py` build share (~1,126L). The mix ⇄ `junction_snip_qa` hardening. | ~35 / ~330 |
| **W2c** | `build` | ~3,600 | `delivery_guardrails.py` build share (~1,975L) + `artifact_repairs.py` build share (~1,345L) + `artifact_sanitize/registry.py` build share. | ~40 / ~400 |
| **W3** | `sound` | ~1,565 | `artifact_sanitize/sound_design_plan.py` (172L, 100% sound), `delivery_invariants` sound share, `artifact_repairs` sound share (~645L), `artifact_sanitize/one_writer.py` sound share. | ~10 / ~90 |
| **W4a** | `plan_rank` | ~2,500 | Phase-pure `artifact_sanitize`: `selection.py` (537L), `transitions.py` (280L), `gap_report.py` (627L), `air_script.py` (597L, 81% plan_rank), `seed_policy.py` (104L). | ~18 / ~150 |
| **W4b** | `plan_rank` | ~2,400 | `artifact_repairs.py` plan_rank share (~1,990L) + `artifact_sanitize/one_writer.py`, `preflight.py`, `halt.py` remainders. | ~20 / ~200 |
| **W5** | `fill_gaps` | ~670 | `identical_failures` fill_gaps share, `heal_routing` fill_gaps share, `artifact_sanitize/coverage_audit.py`. | ~8 / ~60 |
| **W6** | `understand-c` | ~670 | `stage_completion.py` deletable understand-c share. **Gated on §3.1 trap 1.** | ~10 / ~80 |
| **W7** | `understand-b` | ~450 | `execution_invalidation_profiles` understand-b share. | ~5 / ~30 |
| **W8** | `understand-a` | ~670 | `stage_input_checks` deletable share, `artifact_lifecycle` deletable share. | ~10 / ~80 |
| **W9** | `prepare` | ~450 | Residual prepare-attributed symbols. | ~5 / ~30 |
| **W10** | second ring | ~5,309 | §7 modules — only after their callers are gone. | ~25 / ~200 |

W0 should be executed and reviewed on its own. It is 1,516 lines with a provably empty blast radius,
and it calibrates the attribution harness (§5) against a wave whose predicted failure set is *empty*.
If W0 produces a single new failure, the harness is wrong and the campaign stops.

---

## 5. Attribution — the replacement for "zero net-new failures"

**State this plainly: the "zero net-new failures" invariant that has protected every change in this
repo will be deliberately broken by this work.** Mass guardrail deletion will fail hundreds of
tests, and per the operator's ruling, pinned tests are left failing rather than deleted.

The replacement invariant is stricter, not weaker:

> Every new test failure must be **attributable to a specific intentional deletion** and recorded in
> §6 of this document. An unexplained new failure is a bug, not a hole — and stops the wave.

### 5.1 The mechanism: predict before deleting

The attribution is *predictive*, not forensic. For each wave, before a line is deleted:

1. **Baseline node-id set.** `pytest tests/ -q --tb=no` and record the set of failing node ids — not
   the count. The baseline is roughly **208 failures / 4,124 passed** and the suite is mildly flaky,
   so counts are meaningless and set arithmetic is mandatory. Run the baseline twice and treat the
   symmetric difference as the flake set, excluded from both sides.
2. **Predicted failure set.** From the wave's deleted symbol list, compute the reverse-dependency
   closure over `tests/` — every test file importing a deleted symbol, and every test file naming it.
   A module-level deletion fails a test file at *collection*, so the unit of prediction is the whole
   file's test functions. Tooling for this already exists (the AST + reverse-reference scan used to
   build §2 and §4 of this document); it must be committed alongside wave 0 as
   `tools/subtraction_predict.py` so predictions are reproducible months from now.
3. **Delete the wave.**
4. **Actual failure set.** Re-run, subtract baseline and flakes → `ACTUAL_NEW`.
5. **The gate:** `ACTUAL_NEW ⊆ PREDICTED`. Any member of `ACTUAL_NEW \ PREDICTED` is an
   **unexplained failure** — a real bug, not a hole. The wave stops, that failure is diagnosed, and
   the wave is rolled back from the tag if it cannot be explained.
6. **The ledger:** every member of `ACTUAL_NEW` gets a row in §6, classified `PINNED` or
   `SCAFFOLDING`, naming the deletion that caused it.

Set containment rather than equality: `PREDICTED` is deliberately over-broad (a test that merely
mentions a symbol may not exercise it), so predicted-but-passing is fine and expected.

### 5.1a Bisect rules — how to find which deletion broke a test

Both rules were bought with a wasted batch. Both are mandatory.

**Restore cumulatively, against a shim-free base — never one symbol at a time.** Guard chains are
multiple links deep and they fork. `apply_seed_order_heal → seed_order_heal_action →
{live_producer_authority, seed_order_consumer_for}` is two deep with a two-way fork, so *every*
single-symbol probe still left a missing link and every probe reported "still fails". The reading
that invites — "no single symbol explains it, so the module is somehow cursed" — is wrong, and it
cost a 79-line deletion that was mostly sound. Restore symbol 1, test, then 1+2, then 1+2+3. The
first green tells you the chain depth.

**After appending a raising shim, assert the name is absent from the rest of the file.** Python's
last definition wins, so a shim appended at EOF **shadows the real symbol** if the real one is still
above it. Appending the `seed_order_heal_action` shim to an otherwise untouched file breaks the test
on its own. Any bisect that restores a symbol into a file that still carries its shim is measuring
the shim, not the restore. Concretely: after writing a shim for `NAME`, check that
`ast.parse(file)` yields exactly one top-level definition of `NAME`.

A corollary for the planner, from the same class of error: **apply every carve-out before running the
closure.** Carving a symbol back to "surviving" re-pins everything it calls, so a carve applied
afterwards silently invalidates the closure that assumed it was deleted.

### 5.2 Expected new-failure count

Measured by import-level reverse dependency across the whole seed list:

| | Files | Test functions |
|---|---:|---:|
| Test files that **import** a delete-candidate (collection-error risk) | **145** | **1,404** |
| — **PINNED** (`test_i*`/`test_f*`/`test_h*`/`test_end*` prefix ∪ sets `MUX_FORENSICS`) | **67** | **523** |
| — **SCAFFOLDING-eligible** (neither) | **78** | **881** |
| Test files that merely *mention* a candidate (softer risk) | 160 | 1,611 |

**Expected end-state: roughly 500–550 permanently failing pinned tests, and up to ~880 scaffolding
tests either deleted with their code or failing.** The 523 pinned test functions across 67 files are
the precise hole map the operator asked for, and none of them may be deleted.

Per-module import blast radius, for wave sizing:

| Module | Test files | Test fns |
|---|---:|---:|
| `delivery_guardrails` | 56 | 573 |
| `thrash_hardening` | 35 | 293 |
| `artifact_repairs` | 23 | 287 |
| `stage_input_checks` | 16 | 219 |
| `heal_routing` | 25 | 217 |
| `artifact_sanitize` | 26 | 206 |
| `identical_failures` | 12 | 167 |
| `recovery_controller` | 14 | 155 |
| `delivery_invariants` | 7 | 97 |
| `stage_resilience` | 6 | 89 |
| `execution_invalidation_profiles` | 5 | 32 |
| `remediation_framework` | 4 | 13 |
| `forensics_stall` | 1 | 0 |
| `seed_policy` | 0 | 0 |

### 5.3 Test classification rule, restated

Per [contract-migration-test-policy.md](./contract-migration-test-policy.md) and the operator's
ruling:

- **Never delete a pinned test.** Let it fail. 67 files / 523 functions are pinned.
- **Delete only scaffolding** — tests pinning a specific heal route, a `PRODUCER_PIN_TABLE` entry, or
  a retry/cycle count that a contract now decides.
- Every deleted test is classified `PINNED` or `SCAFFOLDING` in the commit message. There is no third
  option. A `PINNED` line is legal only for a *rewrite*.
- Tie-breaker: if it could be either, it is **pinned**.

A collection error takes down a whole file, so a wave that deletes a symbol imported by a pinned file
fails all of that file's tests, not just the relevant one. Where that is avoidable by leaving a
deprecated shim in place, **leave the shim** — a pinned test failing on its own assertion is a
readable hole; a pinned test failing on `ImportError` tells the later patching pass nothing.

---

## 6. Hole manifest — deletions with no proven replacement

The worklist for the patching pass. **Rows are filled in as each wave executes.** The table below is
pre-populated with the holes already identifiable from static analysis; the `Pinned test that will
fail` column is completed from `ACTUAL_NEW` per §5.1 step 6.

Column meaning: *Failure mode now unguarded* is what can reach `master/master.wav` with the guard
gone — that is the question the patching pass must answer for each row.

| # | Deleted | What it protected against | Failure mode now unguarded | Replacement | Pinned test that will fail |
|---|---|---|---|---|---|
| H-01 | `heal_routing.py` (660L, whole) | Stage X failing without a defined repair route to stage Y | A stage fails and nothing routes a repair; the run advances past it on D1 and records a defect. Whether the defect is *correctly classified as ship-bar-degrading* is unproven. | **nothing — hole.** Contract `remediation` edges are not populated; `requires` consumption is still gated behind `MUX_CONTRACT_REQUIRES=0`. | 20 pinned files reference `heal_routing` |
| H-02 | `recovery_controller.py` (1,816L) — 23 orphan + 14 test-only playbooks | Named recovery playbooks for 37 specific observed failure shapes (`seed_order_prereq`, `selection_edl_order_drift`, `mint_reorder_glue`, `upstream_stale_rerun`, …) | Each playbook encodes one exec_11871 lesson. With them gone, the shapes recur and the run advances past them. `playbook_selection_edl_order_drift` (81L) and `playbook_seed_order_prereq` (73L) guard the publishability contract's "selection leads EDL" rule. | **nothing — DECLINED, §6.06.** Superseding the "partial" that stood here: plan §2.3's "seed order unreachable by construction" is **false at HEAD**. Contract `remediation` is read by `stage_resilience` but declares `[volley_retry, full_stage_rerun]` in all 91 contracts — no discrimination among the 37 error classes, no resume stage (rule 2, §0). | 9 pinned files; pinned by `tests/test_recovery_controller_replacement_absent.py` |
| H-03 | `thrash_hardening.py` (3,488L) | Sticky heals, oscillation halts, premature caps, gate-wait ticks, wasted-work detection | The no-delta guard covers the *repeat-identical-input* case only. Oscillation with a changing-but-non-converging input is **not** covered by either the no-delta guard or the attempt memo. | **partial.** `dispatch_delta.no_delta_refusal` + `memo_skip` replace the cap assertions. `note_sticky_heal_attempt` (112L), `record_thrash_hit` (98L), `infer_heal_intent` (70L) have no replacement. | 23 pinned files |
| H-04 | `delivery_guardrails.py` (2,904L) | Delivery-epoch matching, listen-delight waivers, critical residual counting, music-limbo exit, selection-order fingerprints | `delivery_epoch_matches` / `read_delivery_epoch_at_dispatch` guard stale-delivery detection. `master_epoch.py` implements the §5.4 epoch assertion **at the seal only** — mid-pipeline epoch drift becomes invisible between deletion and the `verify_master` check. | **partial.** `master_epoch.py` replaces the seal assertion. Listen-delight waiver logic (`listen_delight_waived_unattended`, `ensure_listen_delight_waiver_unattended`) has **no replacement** and touches the authoritative listen-delight ship gate from NORTH_STAR. | 42 pinned files — the largest single blast radius |
| H-05 | `artifact_sanitize/*` (4,390L, 22 files) | Per-artifact structural sanitation before commit: selection, EDL, transitions, gap report, air script, one-writer enforcement | One-writer enforcement (`one_writer.py`, 454L) is the i13/i14/i15 ownership battleground. `artifact_ownership.write_permitted()` covers *who may write*; `one_writer.py` also covers *concurrent write ordering within a stage*. | **partial.** `artifact_ownership` replaces the authority check. Structural sanitation of artifact *content* (`selection.py` 537L, `gap_report.py` 627L) is **nothing — hole**; contract `sufficiency` is populated for only 41/90 contracts. | 9 pinned files |
| H-06 | `artifact_repairs.py` (5,378L deletable of 6,268L) | In-place repair of malformed artifacts before they reach a consumer | **Revised — this row was wrong.** A malformed artifact produced by a *successful* stage is never a dispatch refusal, so **no defect row is created** and PMQ's `no_open_ship_bar_defects` check passes. D1 does not cover this module at all. See §9.2: Class B, silent. | **nothing — hole.** Requires `record_defect` to be extended to post-dispatch artifact rejection (§9.5). | 2 pinned files |
| H-07 | `execution_invalidation_profiles.py` (715L) | Structural-expansion decisions for invalidation blast radius | Precision invalidation (§5.4) is still `pending` in the plan and activates per-stage gated on conformance-green. Deleting the profiles before precision invalidation lands leaves whole-tail behaviour as the only mode. | **nothing yet — hole with a known owner.** `p15-precision-invalidate` is `pending`. **Do not run W2a's portion of this until that todo completes.** | 1 pinned file |
| H-08 | `seed_policy.py` (104L) | Sticky seed marks and seed-satisfaction policy | Not a silent hole: deleting the module **deadlocks the seed walk**. `llm_flow_hardening`'s only fallback correctly refuses to mark a pass-2 stage with no sidecar, and `gap_framing_recompose` has no fallback at all. | **nothing — DECLINED, not a hole, §6.06.** The concession that `ensure_sticky_seed_mark` "has no equivalent" *is* the whole module — the sticky mark is the enforcement. Stage order is the fixed seed walk; no contract can express "satisfied by policy without an artifact". | 1 pinned file; pinned by `tests/test_seed_policy_replacement_absent.py` |
| H-09 | `forensics_stall.py` (184L) | Stall escalation that blocks the driver | `escalation_blocks_driver` (11L) gated the driver on an escalated stall. Under D1 the run advances instead. | **nothing — rule 1, §0.** `ship_reachable()` is no longer a stub (§12.4), but its *halt* is opt-in: `MUX_SHIP_REACHABILITY_HALT` defaults off (`ship_reachability.py:261`), so the analysis records a verdict and keeps walking. Nothing blocks the driver at current defaults. | 0 pinned files — lowest-risk deletion in the campaign |
| H-10 | `identical_failures.py` (570L deletable) | Repeat-failure fingerprinting and halt management | `record_identical_failure` is **KEPT** (§3). The halt-management half (`clear_halts_matching`, `sync_identical_halts_with_product`, `clear_halts_for_stages_if_predicate_flipped`) is deleted. Halts then never clear, or never set. | **partial.** No-delta guard replaces the *detection*; nothing replaces halt lifecycle management. | 2 pinned files |
| H-11 | `stage_input_checks.py` (705L deletable) | Per-stage input assertions beyond `require_stage_inputs` | Contract `inputs.hard` is populated for only **30 of 90** contracts. Deleting imperative input checks before that reaches 90/90 leaves 60 stages with no input validation at all. | **nothing — hole, and a sequencing error if run early.** W8 is late in the order, which helps, but the gate is contract population (`p1-populate-groups`, `pending`), not wave position. | 9 pinned files |
| H-12 | `delivery_invariants.py` (532L deletable) | Delivery-stage invariants: seed-order consumers, VO line owner sync, live producer authority | `sync_vo_line_owners` (68L) keeps VO line ownership consistent — directly relevant to the G1 VO pickup gate. | **partial.** `committed_master_wav` kept; `live_producer_authority` superseded by `artifact_ownership.owners_of`. `sync_vo_line_owners` is **nothing — hole**. | 2 pinned files |
| H-13 | `remediation_framework.py` (406L deletable) | Remediation plan mutex and honest playbook outcome reporting | `remediation_plan_mutex_allows` stopped two remediation plans running at once. The solver's walk lease (§8.3) is a *different* lock — it serialises walks, not remediation plans. | **nothing — hole.** | 1 pinned file |
| H-14 | `stage_completion.py` (533L deletable of 2,289L) | Stage-done determination and artifact completeness assertion | Most of this module is **KEPT** because `artifact_ownership` needs `producer_pin_for_token`. The deletable share is the heal-pin routing half. | **partial.** `stage_outputs_present` (in `agenda.py`) + contract `outputs` replace the done check. | 45 pinned files — second-largest blast radius |
| H-15 | `artifact_lifecycle.py` (592L deletable) | Staleness stamping and archival (`stamp_stale_and_archive`, 107L), hard-input strictness | Stale artifacts are no longer stamped or archived. Under precision invalidation this is the mechanism that made stale state *visible*. | **partial.** `master_epoch.py` catches staleness at the seal. Mid-pipeline staleness visibility is **nothing — hole**. | 2 pinned files |

### 6.0 W0 rows — dead guards, and what their deadness means

W0 produced zero test failures, so it contributes no failure rows. It did surface two holes that
already existed, which is a distinct and more useful finding: **a guard with no callers is
protection that was already absent.** Deleting it removes no safety, but it does remove the evidence
that the safety was once intended. Both are recorded here so the patching pass can decide whether to
re-wire them.

| # | Deleted in W0 | What it was for | Status of the protection |
|---|---|---|---|
| H-16 | `stage_resilience.before_mark_done` (25L) | "Refuse `mark_done` when staged outputs are incomplete / unacceptable." Called `stage_completion.staged_artifacts_acceptable`. | **Already unguarded before W0.** Zero callers, so nothing has been refusing `mark_done` on incomplete outputs. Plan §8.5 (`done(stage) ⟺ is_done ∧ stage_outputs_present`) is the intended replacement and lives in the solver — but the *writer* side has no such check. A stage can still mark itself done with unacceptable staged outputs. |
| H-17 | `delivery_guardrails.delivery_epoch_matches` + `read_delivery_epoch_at_dispatch` (11L) | "D2: expensive stages must not run after a structural epoch bump." | **Already unguarded before W0.** Dispatch-time epoch checking is not running. `master_epoch` covers the *seal* (default-on, wired into `master_qc.py`), so stale audio is caught before it ships — but only at the very end, after the expensive work has been redone. The D2 rail described in plan §5.4 exists at one of its two intended points. |

Neither is a regression from W0. Both are pre-existing gaps that the campaign should not assume are
covered.

### 6.05 Batch 1 rows — shipped, gate clean

Batch 1 shipped **6 symbols / 75 lines** across four modules and produced **4 new failures, all
predicted, 0 unexplained**. These are live holes now, not projections.

| # | Deleted | What it protected against | Failure mode now unguarded | Replacement | Pinned test now failing |
|---|---|---|---|---|---|
| B1-01 | `thrash_hardening.gate_wait_tick` (27L) | Counting how many ticks a stage sat at a gate, so a stuck gate escalated | A stage can wait at a gate indefinitely without escalation. The door refuses *no-delta* re-dispatch, which is a different condition: a gate that never opens produces no dispatch at all, so there is nothing for the door to refuse. | **nothing — hole.** | `test_anti_footgun_hardening.py::test_gate_wait_escalates` |
| B1-02 | `thrash_hardening.wasted_work_is_true_waste` (21L) | Distinguishing genuinely wasted expensive work from deliberate avoidance | Avoidance and waste are no longer distinguished, so waste accounting cannot drive sticky-halt. Paired with B1-01 this removes both halves of the thrash-escalation signal. | **partial.** `dispatch_delta.no_delta_refusal` covers repeat-identical input only. | `test_anti_footgun_hardening.py::test_avoidance_is_not_true_waste` |
| B1-03 | `identical_failures.structural_failure_signature` (12L) | Fingerprinting a failure by structure (including its predicate) so repeats were recognised across differing messages | Two failures with the same structure but different text are no longer recognised as the same failure. `record_identical_failure` is kept, so detection survives — the *predicate-aware* grouping does not. | **partial.** | `test_residual_cluster_cb.py::test_b04_structural_failure_signature_includes_predicate` |
| B1-04 | `delivery_guardrails._listen_delight_quality_cleared` + `_active_listen_delight_remutate_stages` (8L) | Separating a telemetry-only waiver from a genuine music/delight clearance | A telemetry waiver can read as a delight clearance. This touches the **authoritative listen-delight ship gate** in NORTH_STAR, so it is the highest-value row in this batch despite being the smallest. | **nothing — hole.** | `test_residual_cluster_hardening.py::test_a04_telemetry_waiver_not_music_delight_ok` |

**`delivery_invariants` was dropped from batch 1 — and the reason is now known.** Full writeup:
**[delivery-invariants-anomaly.md](delivery-invariants-anomaly.md)**.

Deleting its four orphan symbols broke
`test_i1_g0_flush_before_gate.py::test_i1_g0_systemexit_flushes_pending_queue` with a seed-order
block on `audio_preclean`. It was **a real dependency, not an artifact.** The seed-order block is
raised on *every* run of that test; the test is normally green because the failure is then healed —
`handle_stage_failure` classifies it `seed_order_prereq` and `playbook_seed_order_prereq` calls
`delivery_invariants.apply_seed_order_heal`, which survived the cut but whose call to the *deleted*
`seed_order_heal_action` was unguarded. The raise was swallowed by `except Exception: recovered =
False` around the playbook dispatch, the heal silently became a no-op, and the original error
surfaced. **The guard stopped guarding, one level removed** — §1.4.4's failure mode, reached through
a surviving caller rather than a direct one.

Two independent reasons the one-at-a-time restores all failed, either sufficient on its own: the
chain is two links deep and forks
(`apply_seed_order_heal → seed_order_heal_action → live_producer_authority` / `seed_order_consumer_for`),
so every single-symbol probe still left a missing link; and the appended raising shim **shadowed the
restore base**, since Python's last definition wins. Both are now standing methodology rules — §5.2.

**Verdict: 3 of the 4 are load-bearing.** Only `_active_listen_delight_remutate_stages` (**3 lines**)
is deletable, proven with a node-id set identical to baseline. Deleting `seed_order_consumer_for`
alone turns three restamp-path tests red. **H-12's "532 deletable lines" for this module is really 3**
without caller rewrites.

One hazard class was retired by the same investigation: an AST scan of `src/interview_mux` found
**zero** computed `getattr` resolving a module symbol, and zero use of `globals()`, `vars()`, `eval`,
`dir()`, `importlib` or `inspect.getmembers`. Dynamic symbol access is not a concern repo-wide, so
a static closure is sound. The real hazard is in-module and inter-candidate call chains, which
`_closure_evict` now covers.

### 6.06 Final wave — both modules DECLINED, zero lines deleted

The last wave attempted the two top-of-stack imperative control modules, `seed_policy.py` (104L) and
`recovery_controller.py` (1,816L). **Both were declined.** It shipped **353 lines of pinning tests and
no deletions** (`3dd0ebf4`), so the §1.4.6 totals stand unchanged. The campaign's own planner reaches
the same verdict independently: `subtraction_predict.py plan --modules seed_policy --modules
recovery_controller` reports `DELETABLE: 0 symbols, 0 lines`.

**H-08 `seed_policy.py` — DECLINED, and not a hole.** A contract declares what a stage must produce
and cannot express "satisfied by policy without an artifact": `sufficiency` is empty for both freeze
stages and no contract field references freeze state. Stage order is the fixed seed walk. So deleting
the module does not open a silent hole — it
**deadlocks the seed walk**, because `llm_flow_hardening`'s only fallback correctly refuses to mark a
pass-2 stage with no sidecar and `gap_framing_recompose` has no fallback. Measured: **2 pre-existing
tests break**, one of them the HF-1 predicate-family pin. Pinned by
`tests/test_seed_policy_replacement_absent.py`.

**H-02 `recovery_controller.py` — DECLINED.** Plan §2.3's "seed order unreachable by construction" is
**false at HEAD**: on a fresh 0.1.0 run `_seed_prereq_block` returns `audio_preclean` for the first
stage dispatched and `dispatch_stage` raises. That confirms the flag
[delivery-invariants-anomaly.md](delivery-invariants-anomaly.md) §6 raised. The other candidate
replacement, contract `remediation`, is read by `stage_resilience` but is uniform across all 91
contracts, so it discriminates nothing (rule 2, §0). Pinned by
`tests/test_recovery_controller_replacement_absent.py`.

### 6.1 Hole accounting

| Category | Count |
|---|---:|
| Deletion groups with a **citable replacement** (contract field, ownership row, door verdict, solver term) | **0 fully** |
| Deletion groups with a **partial** replacement (some symbols covered, some not) | **8** of 15 — was 11; H-02, H-08 and H-09 moved out under §0 rule 1 |
| Deletion groups with **no replacement at all** — pure holes | **5** of 15 (H-01, H-09, H-11, H-13, and the content-sanitation half of H-05) |
| Deletion groups **attempted and DECLINED**, replacement proven absent, zero lines deleted | **2** (H-02 and H-08 — §6.06; H-08 deadlocks rather than opening a hole) |
| Deletion groups **blocked on a pending plan todo** | **3** (H-07 on `p15-precision-invalidate`; H-11 on `p1-populate-groups`; H-09 now gated on the `MUX_SHIP_REACHABILITY_HALT` default rather than on `p15-reachability-real`, which landed — §12.4) |

Not one of the 15 groups has a *fully* citable replacement. That is the honest answer to "how many
deletions will have no proven replacement": **at symbol granularity, the large majority.** The
solver replaces the *policy* — "what do I do when the planner attempted something impossible" — but
it does not replace the ~60 individual artifact-shape lessons those guardrails encode.

---

## 7. Second ring — reached through the call graph, not on the seed list

Found by following callers out of the seed modules. Each is guardrail mass by the same definition
and must be deleted in **W10**, after its callers are gone — deleting them earlier strands the seed
modules mid-wave.

| Module | Lines | Note |
|---|---:|---|
| `edl_narrative_remutate.py` | 1,102 | |
| `execution_contract.py` | 1,030 | **Caution:** `read_active_vo_repair_plan` is called by `ship_reachability.py:312`. Partial keep. |
| `llm_output_resilience.py` | 756 | **Caution:** `artifact_resilience_partial` is called by `artifact_completeness.artifact_status_for_stage`. Partial keep. |
| `llm_flow_hardening.py` | 619 | 14 candidate symbols referenced |
| `execution_status.py` | 570 | |
| `delivery_recovery.py` | 560 | |
| `delivery_unstick.py` | 223 | 11 candidate symbols referenced |
| `execution_invariants.py` | 137 | |
| `audit_repair_loop.py` | 115 | |
| `execution_stall.py` | 99 | |
| `unattended_resume.py` | 98 | |

The two `Caution` rows are additional load-bearing dependencies of the replacement and belong
logically in §3.

---

## 8. Waves that should not proceed as scheduled

Four objections, in order of severity.

1. **W2a must drop `execution_invalidation_profiles.py` entirely — the original objection was
   right for the wrong reason.** `p15-precision-invalidate` has since **landed**:
   `transitive_invalidate()` now has a precision path with a two-sided conformance gate
   (`precision_eligible` on the source, `precision_droppable` on the target), `_blanket_invalidate()`
   preserved verbatim, and a subsequence clamp. That does **not** rescue this deletion, for two
   reasons that are stronger than the original:

   - **The two mechanisms are orthogonal, so precision never supersedes profiles.** Precision
     narrows the *fan-out set* using contract edges. `execution_invalidation_profiles` bounds *which
     paths are archived or cleared* per named remediation profile, with per-profile invocation caps
     (`apply_bounded_invalidation`, `_bump_invocation_count`, `_archive_allowlisted_paths`).
     `artifact_dependency_graph.py` does not reference the profiles module at all. Waiting for
     precision to mature would never have made this deletion safe.
   - **It is not orphan mass.** `apply_bounded_invalidation` and friends have live callers in
     keep-code: `publishability_boundary.py`, `homunculus/agenda.py` (two sites),
     `execution_contract.py` (two sites), `chapter_close_hitch.py`, `post_decision_sanitize.py`,
     `listen_delight_remutate.py`, `stages/segmentation.py`. This is `EXTERNAL_CALLERS` mass, not
     deletable-by-inspection mass.

   **Revised verdict: remove `execution_invalidation_profiles.py` from W2a and reclassify it as a
   second-ring module (§7), deletable only after its seven callers are gone.** The original "hold
   until precision lands" framing was too weak — precision landing changes nothing here.

   Separately, the precision path is real but **inert nearly everywhere**: `STRICT_GROUPS` is
   `("prepare",)`, so eight of nine groups still take the blanket path. Any wave reasoning that
   assumes precision invalidation is active is wrong until that tuple grows.

2. **W8 must not delete `stage_input_checks.py` yet.** Contract `inputs.hard` is populated for
   **30 of 90** contracts. Until `p1-populate-groups` completes, deleting imperative input checks
   leaves ~60 stages with no input validation in either system. This is the one hole that can
   silently produce a hollow master rather than a loud failure: a stage runs on missing inputs,
   writes a structurally-valid but empty artifact, and the solver reads it as a satisfied hard input
   downstream. **Hold H-11 until contract population reaches the relevant group.**

3. **W6 (`understand-c`, `stage_completion.py`) must be sequenced against §3.1 trap 1.**
   `artifact_ownership.py` imports `stage_completion.producer_pin_for_token`. 1,756 of 2,289 lines
   are in the keep closure. The 533-line deletable share must be cut symbol-by-symbol with the
   ownership import verified after each. A module-level cut here takes down the contract system.

4. **W2c is blocked on a dependency, not a pending todo — and the dependency is narrower and
   more alarming than first stated.** `p15-reachability-real` has **landed**: `ship_reachable()`
   is genuine critical-path analysis, not the always-reachable stub. `master_finalize` and `mix`
   now declare real hard inputs. Evaluating the predicate against the current contracts gives:

   ```
   critical_path().requirements:
     ingest/normalized.wav   producer=ingest   required_by=mix
     master/assembly.wav     producer=mix      required_by=master_finalize
   root_producers: (master_finalize,)   unknown_stages: (ingest,)
   ```

   **The critical path to `master.wav` is three stages: `ingest → mix → master_finalize`.** It does
   not contain `full_master_ranking`, `selection_framing_apply`, `edl`, `transitions`,
   `air_script_compose`, `junction_snip_qa` or `assembly_preview`, because `mix.yaml` declares
   `master/edl.json` and `master/selection.json` as **soft** — and soft inputs never gate
   admissibility (plan §2.1). `junction_snip_qa.yaml` still declares `inputs.hard: []`.

   The consequence is precise: **`ship_reachable()` will report the master reachable as soon as
   `ingest/normalized.wav` exists, regardless of whether selection, ranking, EDL or transitions ever
   succeed.** Under D1 the run therefore advances past every failure in the entire selection→EDL
   chain and still believes it is on track to ship. The artifact it produces is a master mixed from
   normalized source audio with no selection applied — structurally complete, and wrong. That is the
   hollow master of plan §9's D1 risk row, reachable today, before any deletion.

   **Revised W2c gate — all three, not just the second:**
   1. `mix` declares `master/edl.json` and `master/selection.json` as **hard** (or the equivalent
      producer edges land such that the selection→EDL chain is on the critical path), and
      `junction_snip_qa` declares real hard inputs;
   2. `critical_path()` re-evaluated and shown to contain the selection→EDL chain;
   3. the PMQ ship-bar refusal path verified end to end (§8.1).

   Populating `mix.inputs.hard` is not cosmetic — per `docs/project-context.md` a stage's hard-input
   set may only ever grow, and `dispatch_delta.hard_input_paths` reads it outside the dependency
   graph, so `MUX_CONTRACT_REQUIRES` does not shield it. This is a real behaviour change and belongs
   to the worker populating `build`/`ship`, not to this campaign.

### 8.1 State of the PMQ backstop — verified

The refusal path exists and is wired: `post_master_quality.py` adds a `no_open_ship_bar_defects`
check from `defect_ledger.defect_summary(ctx)`, and `SHIP_BAR_CRITICAL_STAGES` covers the right
sixteen stages (`full_master_ranking`, `selection_*`, `air_script_*`, `transitions`, `edl`,
`edl_narrative_audit`, `assembly_preview`, `vo_*`, `mix`, `junction_snip_qa`, `master_finalize`,
`master_transcript_build`). The `master_epoch` seal assertion is **default-on**
(`MUX_MASTER_EPOCH_ASSERT`) and wired into `master_qc.py`. Two defects in the backstop:

- **PMQ fails open.** `post_master_quality.py` wraps the defect lookup in
  `except Exception: defects = {"open_ship_bar": 0, "blockers": []}`. Any error reading the ledger
  reports zero open defects and allows publish. The one gate protecting against a hollow master
  fails in the permissive direction.
- **`degrades_ship_bar(stage)` is a static stage allowlist**, not a property of the defect. Whether a
  defect blocks publish depends only on *which stage* recorded it, never on what went wrong.

A fifth, smaller point: the operator's `ship`-first order (vs the plan's `build`-first) is the right
call and should be kept. `ship` is ~5% of the mass with ~110 tests at risk, which makes W1 a cheap
rehearsal of the attribution harness against real deletions before W2 touches 51% of the mass.

---

## 9. The carve-out — silent wrong master vs noticeable gap

This is the axis the operator is deciding on. "Holes patched later" is an acceptable trade when the
hole announces itself. It is not acceptable when the hole ships a wrong master quietly, because a
silent wrong master is the single outcome this project exists to prevent.

### 9.1 The discriminator

The safety net the campaign relies on is D1: advance past a blocker, record a defect, let PMQ refuse
publish. Reading `dispatch_door.record_defect` against `post_master_quality`, that net has one
precise shape:

> **A defect is recorded when a stage cannot be dispatched. Nothing is recorded when a stage
> dispatches successfully and produces a semantically wrong artifact.**

That single sentence partitions the campaign:

| | Guard prevents | Deletion causes | Detected by | Verdict |
|---|---|---|---|---|
| **Class A** | a stage from **failing to run** | dispatch refusal → defect row → PMQ blocks publish | defect ledger + PMQ | **NOISY** |
| **Class B** | a stage from **running successfully on bad data, or emitting bad output** | a well-formed artifact that is wrong | *nothing* | **SILENT** |

Class B is invisible because every remaining detector accepts it. Schema validation passes — an
empty list is valid JSON. Sufficiency covers only 41 of 90 contracts. `ship_reachable()` cannot see
it (§8, item 4). The epoch assertion checks *derivation freshness*, not *content correctness*. And
no defect is ever recorded, so PMQ's `no_open_ship_bar_defects` check passes cleanly.

Secondary test, for anything ambiguous: **does the failure change the bytes of `master/master.wav`
without changing the run's success/failure status?** If yes, Class B.

### 9.2 CARVE OUT — Class B, silent wrong master

**Recommendation: exclude these from the campaign, or gate each on a named replacement.** Roughly
**11,200 lines**, and they are the majority of the plan_rank and sound waves.

| Deletion | Lines | Wave | What goes wrong, silently |
|---|---:|---|---|
| `stage_input_checks.py` deletable share | 705 | W8 | Stage runs with missing inputs and writes a structurally-valid empty artifact. Contract `inputs.hard` covers **30 of 90**, so ~60 stages have validation in neither system. Downstream the solver reads the empty artifact as a *satisfied* hard input. This is the cleanest silent-hollow-master path in the repo. |
| `artifact_sanitize/selection.py` | 537 | W4a | Malformed or mis-ordered selection passes to EDL. Violates the publishability contract's "selection leads EDL, no zero-ms keeps" with no detector — and `mix` treats `selection.json` as *soft*, so reachability never notices. |
| `artifact_sanitize/edl.py` | 147 | W2a | Malformed EDL renders wrong audio. Same soft-input blindness. |
| `artifact_sanitize/gap_report.py` | 627 | W4a | Gap report content sanitation; the i13/i14/i15 battleground. |
| `artifact_sanitize/air_script.py` | 597 | W4a | Air script/seam content — directly determines what is spoken in the master. |
| `artifact_sanitize/transitions.py` | 280 | W4a | Transition content; audible, undetected. |
| `artifact_sanitize/one_writer.py` | 454 | W4b | Concurrent write ordering *within* a stage. `artifact_ownership.write_permitted()` covers who may write, not in what order. Last-writer-wins silently. |
| `artifact_sanitize/*` remainder | ~1,748 | W2a/W3/W4 | Same class. |
| `artifact_repairs.py` deletable share | 5,378 | W2c/W3/W4b | ~60 per-artifact repairs. Under D1 an unrepaired malformed artifact is *not* a dispatch failure — the stage already succeeded — so no defect row is created. The §6 H-06 claim that "D1 + defect ledger replace the policy" is **wrong for this class**: the ledger never sees it. |
| `artifact_completeness` `_gaps_*` table | ~430 | (keep) | Already in §3, restated here because it is the worst instance: the public symbol survives while silently degrading to file-exists, poisoning the solver's sufficiency term with no error anywhere. |
| `artifact_lifecycle.stamp_stale_and_archive` | 107 | W8 | Stale artifacts stop being stamped, so downstream reads stale content as fresh. With `STRICT_GROUPS = ("prepare",)` the blanket path is still active, which masks this until precision spreads — then it becomes live. *Worker-owned file; not this campaign's to cut.* |
| `delivery_invariants.sync_vo_line_owners` | 68 | W3 | VO line ownership drift — wrong voice attached to a line. Audible in the master, detected by nothing. |

### 9.3 PROCEED — Class A, noticeable gap

**These are genuinely "patch it later" deletions.** Roughly **8,900 lines**. Each failure surfaces
as a defect row, a halt, a stuck stage, or a longer run — annoying, attributable, not silent.

| Deletion | Lines | Wave | How it announces itself |
|---|---:|---|---|
| `thrash_hardening.py` | 3,488 | W2b | Oscillation returns as *slower runs* and no-delta refusals — visible in the ledger. Worst case is wasted time, not wrong output. |
| `recovery_controller.py` | 1,816 | W1/W2b | A playbook not firing means the failure shape recurs as a *failure*. Loud by construction. |
| `delivery_guardrails.py` build/ship share | ~2,300 | W1/W2c | Mostly dispatch-time gating → refusal → defect row. **Exception:** the listen-delight waiver logic is Class B (it waives the authoritative ship gate) — carve that out. |
| `heal_routing.py` | 660 | W2b | No heal route → stage fails → defect row → PMQ blocks. The plan's "unreachable by construction" claim holds for `seed order`. |
| `identical_failures.py` halt-lifecycle share | 570 | W2a | Halts never clearing is *maximally* loud — the run stops. Fails safe. |
| `forensics_stall.py` | 184 | W1 | Stall not escalated → run continues → visible in ledger. Zero pinned tests. Lowest-risk deletion in the campaign. |
| `seed_policy.py` | 104 | W4a | Seed ordering breaks → solver refuses → structural halt with an unmet-dep payload. |
| `remediation_framework.py` deletable share | 406 | W2c | Two remediation plans racing produce conflicting writes → `authority_denied` from ownership → loud. |
| `stage_resilience.py` deletable share | 309 | W2a | Flush-path hooks are kept (§3); the rest is reporting. |
| `stage_completion.py` deletable share | 533 | W6 | Heal-pin routing; failures surface as unrouted heals. Sequencing caveat in §8 item 3 still applies. |

### 9.4 The minimum carve-out

If the operator wants the smallest possible exclusion rather than all of §9.2, this is the
irreducible core — the deletions where a silent wrong master is not merely possible but *likely*,
because the guard is the only thing standing between bad content and `master.wav`:

1. **`stage_input_checks.py`** (705L) — gate on contract `inputs.hard` reaching the stage's group.
2. **`artifact_sanitize/selection.py` + `edl.py`** (684L) — gate on `mix` declaring EDL/selection as
   hard inputs, which is the same gate as W2c.
3. **`artifact_sanitize/air_script.py` + `transitions.py`** (877L) — gate on a sufficiency rule for
   air-script and transition content.
4. **`artifact_repairs.py`** (5,378L) — gate on defect recording being extended to cover
   *post-dispatch artifact rejection*, not just dispatch refusal. Without that extension, D1 does not
   cover this module at all.
5. **`artifact_completeness` `_gaps_*`** — already keep-listed; must never be partially deleted.

**Total minimum carve-out: ~7,644 lines.** The remaining ~21,500 lines of the campaign can proceed
on the "holes patched later" basis.

### 9.5 The cheapest way to shrink the carve-out

Item 4 above is the single highest-leverage fix. If `record_defect` were extended so that a stage
which *succeeds* but whose output fails `artifact_status_for_stage` also records a ship-bar defect,
then most of Class B collapses into Class A — the ledger would see bad content, and PMQ would refuse.
That is a small change to the door plus a sufficiency call on the commit path, and it would convert
roughly 6,000 lines of carve-out into safe deletions. It also needs the PMQ fail-open in §8.1 closed,
or the whole net can be bypassed by an exception.

---

## 10. Per-wave gate checklist

Every wave, in order. A wave that cannot tick every box does not run.

**Before**
1. Tree is quiet — no other worker holds a file in the wave's module set. (W0's one flaky node id
   came from a live worker; see §1.4.3.)
2. Re-mint `pre-subtraction-snapshot-full-<wave>` via the temp-index method, **with a retry loop**,
   and verify the new-system modules are inside it by `git cat-file`.
3. `python tools/subtraction_predict.py orphans --json <wave>.json` — strict mode, never `--loose`.
4. Cross-check the wave's symbols against §3 (load-bearing) and §9.2 (carve-out). Any overlap is
   removed from the wave, not argued about. Re-read the wave's §6 *Replacement* cells against the two
   rules in **§0** — a cell that fails either one is **nothing**, and the deletion does not run.
5. `python tools/subtraction_predict.py predict <wave>.json --json predicted.json`.
6. Two baseline `pytest tests/ -q --tb=no` runs; record both.

**During**
7. Delete only the scanned symbol set. No cascades, no opportunistic tidying — cascades belong to the
   next wave (§1.4.2).
8. Pure deletion: `git diff <tag> -- <files>` shows zero added lines.
9. Each edited module still parses and imports; `solver`, `ship_reachability`, `dispatch_door`,
   `artifact_ownership` still import.

**After**
10. One `pytest tests/` run.
11. `python tools/subtraction_predict.py compare --baseline … --baseline2 … --after … --predicted …`
    must print **GATE PASSED**. Any unexplained failure → roll back from the tag.
12. Every NEW failure gets a §6 row, classified `PINNED` or `SCAFFOLDING`.
13. Re-run `orphans` to capture the cascade tail for the next wave.
14. Commit message lists every deleted test with its classification.

---

## 11. Definition of done for `p3-subtract` — MET, campaign CLOSED

**Closed after 427 gross lines removed / 21 added / 406 net**, across **19 symbols** (W0 12 + batch 1
6 + closeout 1), per the tables in §1.4.6. Those are the authoritative figures; the narrower
"~410 lines of guardrail logic" is approximate and carries the caveat in §1.4.6c. Every
wave passed its attribution gate; the closeout deletion had zero new failures by node-id set
comparison, on 4,693 tests collected before and after. `DELETABLE` is now **0 symbols / 0 lines** —
the no-rewrite set is exhausted, not abandoned. The final wave tested that claim from the other end:
it attempted the two top-of-stack control modules and **declined both, deleting nothing** (§6.06). The
remaining 8,710 lines are scoped as a successor refactor in §12.

Criteria as originally written, all met:

1. Every wave's `ACTUAL_NEW ⊆ PREDICTED`, demonstrated by node-id set arithmetic, with zero
   unexplained failures carried forward.
2. Every member of every `ACTUAL_NEW` has a row in §6.
3. Zero pinned tests deleted. 67 pinned files remain in the tree, failing, as the hole map.
4. Every deleted test classified `PINNED` or `SCAFFOLDING` in its commit message; no `PINNED`
   deletions except rewrites.
5. §3 keep-set intact: `pytest tests/test_brain_020_deterministic_control_plane.py
   tests/test_contract_conformance.py tests/test_contract_ownership_xcheck.py
   tests/test_artifact_ownership_constitution.py` no worse than baseline after every wave.
6. `tools/subtraction_predict.py` committed, so §5.1 predictions are reproducible.

---

## 12. Successor work item — retiring the EXTERNAL set (NOT part of `p3-subtract`)

**Status: proposed, unauthorised, unscheduled.** This is a separate piece of work with a different
shape and a different risk profile from the campaign above. It is written here so the next
implementer inherits the analysis rather than repeating it. **Do not treat it as a continuation of
`p3-subtract`, which is closed.**

### 12.1 What the EXTERNAL set is

**256 symbols / 8,710 lines across 12 modules.** These are guardrails that the contract system,
dispatch door and solver have genuinely superseded *by policy* — the campaign's premise about them
holds, **with two proven exceptions: `seed_policy` and `recovery_controller`, where no supersession
exists at current flag defaults (§6.06).** What makes the rest different from everything this
campaign deleted is that **they still have live call sites in ordinary pipeline code.** They are not dead. Deleting one without touching its callers
does not remove a guard; it breaks a caller.

So the unit of work is not "delete a symbol" but "**rewrite the call site, then delete the symbol**"
— which is a refactor, and has to be planned, reviewed and tested as one.

### 12.2 Why removal is silent rather than loud — read this first

The single most important thing to know before starting. These call sites are, again and again, of
this shape:

```python
try:
    from interview_mux.heal_routing import resume_stage_for_error_class
    return resume_stage_for_error_class("g1_vo_incomplete", default="vo_synthesize")
except Exception:
    pass
```

Two properties combine badly:

- the import is **function-local**, so a file-level reference scan attributes it to the importing
  module and can discount it (this is precisely the bug in §1.4.4);
- the call is wrapped in a **broad `except`**, so a missing symbol raises `ImportError` or
  `NotImplementedError` and is *swallowed*.

The result is that removing the symbol does not crash and does not turn the suite red. **The guard
silently stops guarding, and everything still looks fine.** This is the exact failure this campaign
exists to prevent, and it is the default outcome of a careless deletion here. It is also how the
`delivery_invariants` anomaly reached a *surviving* caller two links away
([delivery-invariants-anomaly.md](delivery-invariants-anomaly.md)).

Practical consequences for whoever does this work:

1. **Grep for function-local imports, not just top-level ones.** `rg "^\s+from interview_mux\."`.
2. **A green suite is not evidence.** Removing a swallowed guard leaves the suite green by
   construction. Require positive evidence that the replacement contract rule fires — a test that
   fails when the rule is removed.
3. **Rewrite the `except Exception: pass` while you are there.** If a call site is worth keeping, it
   is worth failing loudly. Most of these broad excepts are load-bearing only by accident.

### 12.3 Per-module sizing

Ordered by size. `caller files` is the number of distinct source files holding live references — the
best single proxy for blast radius, and the number that should drive sequencing.

| Module | Symbols | Lines | Caller files | Notes for the implementer |
|---|---:|---:|---:|---|
| `thrash_hardening` | 48 | 2,447 | 15 | Largest by lines. Sticky heals, oscillation halts, premature caps. `dispatch_delta.no_delta_refusal` covers only repeat-identical input; non-converging oscillation is **not** covered (H-03). |
| `delivery_guardrails` | 43 | 1,761 | 30 | **Widest blast radius — 30 caller files.** Contains listen-delight waiver logic touching the NORTH_STAR ship gate; much of that is Class B and already carved. Do this one last. |
| `recovery_controller` | 49 | 1,290 | 7 | Named playbooks for 37 observed failure shapes. Best symbol/caller ratio in the set, which made it the natural starting point — **but it was attempted and DECLINED (§6.06).** |
| `identical_failures` | 30 | 744 | 14 | `record_identical_failure` is KEPT (§3). The halt-lifecycle half has no replacement (H-10). |
| `heal_routing` | 6 | 453 | 4 | Only 4 caller files. Blocked on contract `remediation` edges being populated, which they are not. |
| `delivery_invariants` | 16 | 427 | 10 | Chain-heavy — see the anomaly writeup before touching it. `sync_vo_line_owners` is Class B. |
| `stage_completion` | 17 | 388 | 12 | Most of the module is KEPT; `artifact_ownership` needs `producer_pin_for_token`. |
| `stage_resilience` | 12 | 358 | 10 | `registry_coverage` pins `all_pipeline_stage_ids`; v2 config orders are the SSOT replacement. |
| `remediation_framework` | 13 | 328 | 13 | Plan mutex is **not** the solver walk lease — different lock, different scope (H-13). |
| `execution_invalidation_profiles` | 8 | 290 | 6 | **Gated: do not start until `p15-precision-invalidate` lands.** |
| `forensics_stall` | 9 | 149 | 8 | Depends on `ship_reachable()` being real rather than a conservative stub. |
| `seed_policy` | 5 | 75 | 3 | Smallest, and was first in the suggested order — **attempted and DECLINED (§6.06).** Solver seed ordering is inert at current flag defaults; sticky marks have no equivalent, and that mark *is* the enforcement. |

**Audit hygiene: these caller counts undercount — read them as a floor, not a measurement.** They
appear to include only production Python importers, excluding tests and shell-script audit targets.
Re-measured for `recovery_controller`: **7 production / 17 test / 2 shell**, not "7". Since §12.4
sequences on this column as a blast-radius proxy, re-measure all three classes before trusting the
order.

### 12.4 Suggested sequencing and preconditions

Sequence by **caller-file count ascending**, not by line count — the cost and risk are in the call
sites. That gives `seed_policy` (3) → `heal_routing` (4) → `execution_invalidation_profiles` (6) →
`recovery_controller` (7) → … → `delivery_guardrails` (30) last.

**Two entries in that order are no longer pending — they are proven undeletable at current flag
defaults.** `seed_policy` and `recovery_controller` were attempted and declined (§6.06), so they are
not work waiting to be started: they are work that cannot start until contract `remediation`
discriminates among failure classes. With `heal_routing` also
blocked below, the first startable module is `execution_invalidation_profiles` (6).

One module is **blocked on other work** and must not be started early:

- `heal_routing` — blocked on contract `remediation` edges being populated.

Two blockers listed here have since **cleared**, and the modules they gated are now sequenced on
caller-file count like the rest:

- `execution_invalidation_profiles` — was blocked on `p15-precision-invalidate`. That has landed:
  `precision_invalidate_enabled()` (`artifact_dependency_graph.py:540-545`) returns `True` when the
  env var is unset, i.e. precision invalidation defaults **ON**, with the per-stage
  `precision_eligible` / `precision_droppable` gate as the safety. Note the per-stage gate keys on
  `contract_conformance.STRICT_GROUPS`, so precision is inert for any group still report-only.
- `forensics_stall` — was blocked on `p15-reachability-real`. That has landed too:
  `ship_reachability.py` is a full 733-line implementation and `ship_reachable(ctx)` decides on
  `master_committed` / `severed_requirements`, not on `unknown ⇒ reachable`.

And one precondition applies to the whole item: **contract `inputs.hard` is populated for 42 of 91
contract files** (91 `*.yaml`, of which `_arbiter.yaml` is not a stage) and `sufficiency` for 43 of
91. Only 11 files are fully hollow — no inputs, no outputs — and **none of the 11 is a pipeline
stage**: they are `meta` sub-volleys, two `gate` non-stages and `_arbiter`. Until coverage reaches
91/91, removing imperative input validation leaves stages with no input checking at all (H-11). *The
replacement must exist before the original is removed* — which, on the evidence of this campaign, is
the rule that most wants stating explicitly. **§0 defines what "exist" means:** on by default, and
discriminating.

### 12.5 Tooling the successor inherits

`tools/subtraction_predict.py` is correct as of campaign close and encodes four rules bought with
wasted waves (see its module docstring). For this work item specifically:

- `plan --json` emits an `external` array with a `callers` field per symbol — the call sites to
  rewrite.
- `_closure_evict` will keep evicting these symbols as long as their callers survive. **That is
  correct behaviour, not a bug**: once a call site is rewritten, the symbol drops into `DELETABLE` on
  the next run. The tool doubles as the progress meter — the work is done when `EXTERNAL` reaches 0.
- `predict` / `compare` still give the `ACTUAL_NEW ⊆ PREDICTED` gate per module.
