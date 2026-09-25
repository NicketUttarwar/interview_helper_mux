# Gap-fill context injection — capability gap

**Status: absent since 2026-07-20.** Findings record only. No code change accompanies this document;
whether to restore the capability is an open decision.

**Verdict in one line:** gap *detection* is fully live, but nothing tells the model what is already
satisfied, so every re-run of an analysis stage regenerates blind instead of returning patches.

**Related:**

- [artifact-generation-and-validation.md](./artifact-generation-and-validation.md) — the contract this gap breaks
- Guardrail subtraction later deleted the already-orphaned injector; the gap predates that campaign

---

## 1. Timeline

| When | Commit | What happened |
|---|---|---|
| 2026-07-17 | `f4ec8bcb` ("codepush") | Chain live. `stages/analysis_stage.py:14` imports `attach_gap_fill_to_input`; line 172 reads `stage_input = attach_gap_fill_to_input(ctx, stage_key, build_stage_input(ctx))`. |
| **2026-07-20** | **`f99f228b`** ("full reset. full refresh v2") | `stages/analysis_stage.py` rewritten to the v2 `llm_simple` path — **+14 / −572**. Both the import and the call are dropped. No replacement injection point added. **This is the death certificate.** |
| 2026-07-20 → 2026-09-16 | — | `attach_gap_fill_to_input` sits as an orphan for ~2 months. No caller, no test, no packet. |
| 2026-09-16 | `a31c0f81` (subtraction wave W0) | The orphaned `attach_gap_fill_to_input` definition is deleted. Correct call: at baseline snapshot `750f112c` the symbol appeared only in its own definition plus two stale doc mentions — no dynamic dispatch, no module `__getattr__`, no `globals()[...]` lookup. |

**The subtraction campaign is exonerated.** It was suspected and disproven. W0 removed a corpse, not a
capability; the capability had been dead for two months at that point. This is also **not** the
`delivery_invariants` "guard silently stopped guarding" pattern — no test ever covered the injection,
so no guard was ever in force on this chain.

---

## 2. Current state

| Piece | Where | State |
|---|---|---|
| `attach_gap_fill_to_input` | (was `artifact_completeness.py`) | **Deleted.** Correctly — orphan since 2026-07-20. |
| `build_gap_fill_context` | `artifact_completeness.py:813` | **Intact, zero callers.** Needs no restoration; it is ready to call. |
| `gap_fill_context` parameter | `required_response_format.py:94` (`build_required_response_block`), `:156` (`volley_format_footer`) | **Still declared, never supplied.** |
| Live call sites of those formatters | `island_cluster_structure.py:814`, `prompt_validation.py:325`, `stages/llm_runner.py:122`, and the internal one at `required_response_format.py:159` | All four **omit** the argument. None goes through a `**kwargs` splat, so nothing can supply it indirectly. |

The chain is therefore broken at **both** ends: nothing builds the block into stage input, and nothing
passes it to the formatter.

**Empirical confirmation.** A repo-wide scan of the run record under `ASSETS/executions` for the JSON
key `"gap_fill_context"` returns **zero** files. Every occurrence of the string anywhere in the tree is
system-prompt boilerplate (backticked prose), never an injected payload key.

**Test coverage.** `tests/test_required_response_format.py:72` hand-builds a `gfc` dict and passes it
directly to the formatter at line 76. That covers the *formatting* branch only. Nothing ever exercised
the injection, which is why the loss was silent.

---

## 3. Why it matters

Gap **detection** is fully live and unaffected:

- `compute_gaps` feeds `should_run_stage_for_artifact` — `pipeline.py:575`, `:753`, `:806` (also `:936`, `:1042`).
- `merge_artifact` still deep-merges on persist — `artifact_writes.py:134`, `:294`.

What is missing is **telling the model what is already satisfied.**

Consequence: when a stage re-runs against a partial artifact, the model **regenerates blind** and the
merge layer absorbs a full rewrite, instead of the model returning patches for the listed `gaps` while
leaving `skip_fields` alone. Cost, latency and drift all land on every incomplete-artifact re-run —
and the re-run rule guarantees those happen.

This was never framing-specific. The old injector was generic over analysis stages keyed by
`STAGE_ARTIFACT_DISK_PATHS`, which includes `missing_framing` (`understanding/gap_evaluations.json`),
`gap_framing_compose` and `gap_report_sanitize` (both `understanding/gap_report.json`).

### 3.1 Prompts instruct the model about a block it never receives

Six **live** prompt files still carry gap-fill instructions. Verified by grep on 2026-09-16:

| File | Line |
|---|---|
| `docs/prompts/_shared/analysis-preamble.system.txt` | 30 |
| `docs/prompts/understanding/speaker-roles.system.txt` | 3 |
| `docs/prompts/understanding/content-context.system.txt` | 5 |
| `docs/prompts/understanding/content-brief-reanchor.system.txt` | 5 |
| `docs/prompts/segmentation/boundary-detection.system.txt` | 3 |
| `docs/prompts/segmentation/segment-classification.system.txt` | 3 |

Every analysis packet therefore carries instructions for absent data.

Three further matches exist but are **not** live prompt text:

- `docs/prompts/understanding/content-context.tbiy.system.txt:16` and
  `docs/prompts/understanding/content-brief-reanchor.tbiy.system.txt:21` — TBIY dual prompts are
  heritage-only and are never loaded: `production_profile.prompt_variant` (`production_profile.py:65`)
  rewrites any `.tbiy.system.txt` path back to the plain `.system.txt`.
- `docs/prompts/analysis-stage-matrix.md:9` — index prose, not a prompt.

No prompt file is edited by this document.

---

## 4. Suggested fix — unvalidated, for the record

**Location:** `run_llm_stage_simple` in `src/interview_mux/llm_simple.py:199`. The payload is built at
line 211 (`base_input = build_stage_input(ctx)`) and serialized at line 235
(`user_payload = json.dumps(base_input, ...)`). A single call between those two points restores the
chain for every stage that routes through this function — which is all of them.

Insert **before** the `volley_packet_lint` / `gap_packet_guard` block at lines 213–227 so the injected
block is linted and captured in the persisted volley input like any other key:

```python
from interview_mux.artifact_completeness import build_gap_fill_context

gfc = build_gap_fill_context(ctx, stage_key)
if gfc:
    base_input = {**base_input, "gap_fill_context": gfc}
```

`build_gap_fill_context` already returns `None` for stages absent from `STAGE_ARTIFACT_DISK_PATHS`, so
no stage-key allowlist is needed.

> **This is unvalidated.** It changes LLM packet content on every analysis stage and **no pipeline run
> has been performed**. It needs a real run to assess: packet size against `gap_fill_cap`, interaction
> with `lint_llm_user_payload` and `assert_gap_packet_richness`, whether patch-only responses survive
> `validate_stage_artifacts`, and whether the six prompts' instructions still match the emitted shape.
> Treat the snippet as a starting point, not a patch to apply blind.

Optionally, the formatter side can be reconnected too — `build_required_response_block` and
`volley_format_footer` already accept `gap_fill_context` — but the input-side injection is the part
that was lost and is sufficient on its own.

---

## 5. Corrections to figures in circulation

- **`STAGE_ARTIFACT_DISK_PATHS` has 72 entries, not 109.** Counted by import on 2026-09-16. The three
  gap-family stages named in §3 are present in all readings; only the total was overstated.
