# Refinement Passes (canon)

> **North star:** absolute best listener outcome for *this* unknown source tape. Refinement Pass is a systemic pillar: discover tape character (L0), gate specific functions (L1), accept only improvements (champion), never loop (one second-run per CFI), never dead-end G1/delivery (flow integrity).

## Architecture

1. **L0 agenda** (`understanding/refinement_agenda.json`) — draft after `episode_structure_compose`, confirm after `full_master_ranking`
2. **L1 gate** (`understanding/refinement_plan.json`) — full auto activate|skip per pass
3. **CFI + ledger** — `understanding/refinement_ledger.json`; max one refinement per CFI per run
4. **Blacklist / whitelist** — default deny; blacklist wins (`analysis.refinement_passes`)
5. **Champion** — `understanding/refinement_champion/`
6. **Evidence packets** — `understanding/refinement_evidence/{pass_id}.json`
7. **Shadow score** — ON by default when Pass 2 skipped (`understanding/refinement_shadow/`)
8. **Flow integrity** — skip-copy draft→final so G1 always reachable

## Flagship path

```
gap_framing_compose (draft) → ranking (soft framing hints)
  → refinement_agenda confirm
  → gap_framing_recompose OR skip-copy
  → selection_framing_apply
  → G1 (draft or final lines)
  → transitions (+ optional refine stubs)
```

## No spend caps

Refinement passes are **deterministic, local rewrites** (candidate-vs-champion comparisons, drop/keep decisions, snapshot diffs) — not additional LLM calls. The only anti-loop control is the **CFI ledger cap** (max one *refinement* call per Canonical Function Identity per run; see below). There is no token/cost/latency budget, no per-run spend ceiling, and no operator cost-approval step for Pass 2 — full auto always runs to completion or skip.

## GUI

- Steps list is **always visible** (no Needs-you-only filter, no hide skipped gap stages)
- No cost/latency estimate UI
- Full auto when L1 activates (no approve modal)
- Refinement agenda strip shows tape character + eligible classes above the step list
- Outcome trajectory: `understanding/listener_outcome_trajectory.json` + log alerts

## Multilingual

Runtime language fields are **docs-only** for now — see [multilingual-support.md](./multilingual-support.md). Policy packs may grow language hints later.

## Priors

`analysis.refinement_passes.priors.enabled: soft` (default ON). Soft-bias L0 only; L1 still needs this-run evidence — a prior can only **add** an eligible class, never remove one or force an `activate` decision. Store: `ASSETS/refinement_priors/priors.json` (gitignored, per-`tape_character` accept-rate rows updated by `refinement_priors.record_outcome`).

## Succession & mutex

`analysis.refinement_passes.succession` in the catalog config governs pass ordering within a run:

- **Unlocks** — e.g. `transitions_refine` and `sdp_intent_refine` only unlock `after_accept_or_skip_copy: gap_framing_recompose` (flow integrity guarantees this always resolves); `ranking_refine` unlocks `after_signal: post_gap_topic_holes` (coverage audit still shows uncovered topics after the gap pass).
- **Mutex** — `narrative_arc_refine` and `ranking_refine` are mutually exclusive when both would reorder the same run (whichever is done or activated first blocks the other via `refinement_succession.mutex_blocked`).
- **Priority** — tie-break order when multiple passes are simultaneously eligible: `gap_framing_recompose → selection_framing_apply → ranking_refine → narrative_arc_refine → transitions_refine → sdp_intent_refine → edl_narrative_refine`.

## Shadow score

`analysis.refinement_passes.shadow_score.enabled: true` (default ON). Whenever a pass is **skipped** (blacklist, whitelist, cap, agenda, succession, mutex, or no-new-evidence), `refinement_shadow.maybe_write_shadow_score` writes an informational-only draft-vs-final line-count comparison to `understanding/refinement_shadow/{pass_id}.json`. It never blocks, gates, or changes a decision — purely observability for "what a Pass 2 might have changed."

## Mid-pass / ensemble / cold-open

- **Mid-pass** (`refinement_midpass.py`) — long recomposes shard lines by act/chapter inside **one** CFI count; first-shard failure quarantines and keeps champion.
- **Ensemble lint** (`refinement_ensemble.py`) — after `transitions_refine`, flags bridges that echo gap VO text → `understanding/refinement_ensemble_lint.json`.
- **Cold-open audition** (`refinement_cold_open.py`) — optional 20–40s listen plan → `understanding/cold_open_audition.json` after gap finalizes.
- **`--from-stage`** — `RunContext.clear_from` resets ledger counts for cleared stages via `reset_ledger_from_stages`.

## Modules

| Module | Role |
|--------|------|
| `refinement_identity.py` | CFI registry — one row per function, acyclic `refines_cfi` graph |
| `refinement_ledger.py` | Ordered call ledger; `max_second_runs_per_cfi` (default 1) cap enforcement |
| `refinement_catalog.py` | Pass catalog, black/white lists, succession config defaults |
| `refinement_policy.py` | Tape character detection + policy packs (eligible-class defaults per character) |
| `refinement_priors.py` | Soft anonymized priors biasing L0 (never removes eligibility) |
| `refinement_succession.py` | Unlock rules + mutex checks between passes |
| `refinement_agenda.py` | L0 — draft/confirm eligible-class agenda |
| `refinement_gate.py` | L1 — full-auto activate\|skip decision + input-hash snapshotting |
| `refinement_evidence.py` | Read-only evidence packet a pass reasons over |
| `refinement_kernels.py` | Deterministic scoring kernels (VO budget, rubric compare, report delta) |
| `refinement_champion.py` | Per-domain champion store (best-known artifact + score vector) |
| `refinement_accept.py` | Candidate vs. champion accept/reject (noop guard, feasibility, rubric) |
| `refinement_cascade.py` | Downstream invalidation list after an accepted candidate |
| `refinement_shadow.py` | Informational shadow score when a pass is skipped |
| `refinement_outcome.py` | Listener outcome trajectory log (`understanding/listener_outcome_trajectory.json`) |
| `refinement_passes.py` | Stage runners — recompose, apply, and stub refine passes |
| `refinement_flow_integrity.py` | Skip-copy draft→final so G1/delivery never dead-end |

## Class ownership (short)

| Class | Pass | Listener job | Kernels | Champion domain | Succession |
|-------|------|--------------|---------|-----------------|------------|
| gap_vo | gap_framing_recompose | Host glue on kept order | VO budget, orphan feasibility, listener rubric | `gap_vo` | Unlocks transitions/sdp after accept or skip-copy |
| ranking | ranking_refine | Topic survival / pacing | topic_survival | ranking selection | Mutex with narrative when both reorder |
| narrative | narrative_arc_refine | Chapters match air | comprehension_risk | narrative_plan | Mutex with ranking |
| transitions | transitions_refine | No duplicate bridges | volley integrity + ensemble lint | transitions | After gap path resolves |
| sdp_intent | sdp_intent_refine | SFX restraint | feasibility | sound_design_plan | After frozen VO timeline |
| edl_narrative | edl_narrative_refine | Pre-EDL sanity | listener rubric | edl_narrative_audit | Before `edl` |
| cold_open | (audition plan) | Cold-open listen window | VO budget | gap_vo open lines | When mastering_plan / agenda opens class |

One-pager detail lives in this table + module docstrings; expand later if packs diverge.

## Stage order (delivery)

`refinement_agenda` (confirm) is inserted right after `full_master_ranking`; each `*_refine` stage sits immediately after the first-pass stage it revisits (`src/interview_mux/v2/config.py` `DELIVERY_ORDER`, `src/interview_mux/web/stages.py` `DELIVERY_STAGES`):

```
full_master_ranking → refinement_agenda → gap_framing_recompose → selection_framing_apply
  → ranking_refine → narrative_arc_refine → transitions → transitions_refine
  → sound_design_plan → sdp_intent_refine → sound_design_vo_finalize
  → edl_narrative_audit → edl_narrative_refine → edl → …
```

Every stage above is deterministic — `decide_pass` runs first and most default to `skip` unless the L0 agenda opened that class **and** succession/mutex/cap allow it.

## Schemas

`docs/cross-cutting/json-schemas/` — `refinement_agenda.schema.json`, `refinement_ledger.schema.json`, `refinement_plan.schema.json`. Wired into `prompt_validation.ARTIFACT_WRITE_VALIDATORS` so every `ctx.write_json` to these three paths is schema-checked; see [json-schema-coverage.md](./json-schema-coverage.md).

## API / GUI exposure

- `GET /api/runs/{id}` — top-level `refinement_agenda` (mirrors `understanding/refinement_agenda.json` when present) and `listener_outcome_trajectory` (mirrors `understanding/listener_outcome_trajectory.json` when present).
- `stages[]` entries — `refinement_pass: true` for L0 agenda, gap recompose/apply, and every `*_refine` stage; `pass_of` names the first-pass stage it revisits (e.g. `transitions_refine.pass_of == "transitions"`).
- Frontend: `PipelineStepList` renders a "Pass 2" badge from `stage.refinement_pass` and an agenda strip (tape character + eligible classes) from `run.refinement_agenda`.
