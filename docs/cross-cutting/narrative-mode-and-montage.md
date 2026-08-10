# Narrative mode and montage grammar

Canon for first-class storytelling decisions on `mastering/mastering_plan.json`. Strategy: [mastering-process.md](./mastering-process.md) · Construction: [mastering-construction-decisions.md](./mastering-construction-decisions.md) · Prefer/forbid data: [narrative-mode-prefer-forbid.json](./narrative-mode-prefer-forbid.json) · Priors: [narrative-mode-priors.json](./narrative-mode-priors.json).

**North star:** best finishable, recommendable listen for *this* tape — without inventing unspoken interview dialogue.

## Sole air authority

`narrative_mode` (+ `montage_grammar`) on a valid plan is **sole air authority**. These are **priors/hints only** and never override a confirmed plan:

- `format_class` / `tone_class` (content_context)
- `tape_character` (refinement)
- `production_style` (`documentary_interview` / `tbiy_narrative`)
- Episode-structure packs / `DYN_*` catalog entries

## Modes

| Mode | Listener feel | Typical VO |
|------|---------------|------------|
| `conversational_host` | In-the-room interview | Questions / reactions |
| `guide_summary` | Host guides; tape delivers proof | Summaries + impact clips |
| `documentary_bridge` | Light expository / third-person bridge | Prefaces, story bridges, extracted context |
| `hook_montage` | Teaser energy then body | Cold open + montage glue |
| `sparse_source` | Tape carries | Few bridges only |
| `hybrid_bespoke` | Named blend | Requires in-plan matrix + evidence |

POV: `host_first_person` | `host_second_person` | `expository_third_person` — spoken by the **chosen clone speaker** (prefer pickup/least-spoken; any on-tape speaker with consent).

### Hybrid acceptance

`hybrid_bespoke` requires: `hybrid_label`, ≥2 `evidence_refs`, explicit anti-patterns, and L4 style_fit ≥ pass threshold — else demote to nearest closed mode.

## Montage grammar moves

`vo_then_clip` · `clip_then_react_vo` · `summary_replace_setup` · `cold_open_then_body` · `act_preface_blocks` · `interleaved_bridges` · `information_package_then_block`

Prefer/forbid matrices (JSON) reweight gap `line_category` usage; they do not invent new categories.

## Sonic density by mode

| Mode | Beds / stingers |
|------|-----------------|
| `sparse_source` / `conversational_host` | Minimal; speech-wins |
| `guide_summary` / `documentary_bridge` | Moderate under bridges |
| `hook_montage` | Cold-open stinger/bed allow |
| `hybrid_bespoke` | Declared in plan |

## Two-pass Shape

1. **Pass1 (provisional)** — after brief/topology + best-available research (Waves 1–3+); **before** `missing_framing`. Steers gap search via prefer/forbid.
2. **Pass2 (confirm)** — after gap evaluations (+ ranking when available). May keep or change mode; audit `provisional_mode` → `confirmed_mode`. Downstream binds to confirmed (else provisional > degraded).

Pass2 failure keeps Pass1 or degrades — never dead-ends G1.

## 8-wave research

Research dossier (`mastering/research_dossier.json`) is the primary Shape evidence. Thin compiler packets are fail-open fallback only. See [mastering-research-fields.md](./mastering-research-fields.md).

## Conflict precedence

1. Valid confirmed (else provisional) `mastering_plan`
2. NLE locks
3. `selection.json`
4. `gap_report` lines
5. Deterministic EDL

## Rebuild scopes

| Trigger | Scope |
|---------|-------|
| G0 transcript fix | `plan_gap_rank_edl` |
| Topology / pickup / consent | `plan_gap` |
| NLE structural | `plan_gap_rank_edl` |
| NLE trim-only | `edl` if plan hash valid |
| Redo Shape | `plan_only` (+ dependents as needed) |

## Voice clone

- **Prefer** pickup/least-spoken host
- **Allowed when needed:** any speaker on the recording with consent + reference + scope
- **Forbidden:** inventing unspoken interview dialogue; cloning people not on the tape

## Listen delight

Critics and the standalone `mode_consistency` QC summary remain **advisory** — never block `master_finalize` on their own. `listen_delight_audit` itself is the **authoritative ship gate** (`mastering.listen_delight.mode`, default `authoritative`): it folds `mode_consistency` into its `mode_coherence` dimension, and floor failures hard-stop `listen_delight_audit` and re-block at `post_master_quality`/publish. The human listen rubric mirrors the same floors at sign-off — see [NORTH_STAR.md](../../NORTH_STAR.md#human-listen-rubric-ship-checklist).

## Spoken structure (never air chapter numbers)

Chapters/acts/parts are **business logic and subtext only**. Synthetic VO and transitions must never say “Chapter Four”, “Act 2”, “in this chapter”, or empty show scaffolding (“welcome back”, “in today’s episode”). Thematic hinges only. Enforced by prompts + `spoken_meta_lint` before synth.

## No caps

This workstream must not add spend / timeout / remint / attempt caps under `mastering.shape.*`. Soft-gate keys: `enable`, `mode`, `shadow_compare`, `consumers_bind`, `two_pass` only.

**Hybrid Shape bind (per-run):** Shape synthesize/confirm dynamically emits `ordered_segment_ids` when ready. Global `consumers_bind` stays **false**; delivery prefers Shape order only when the emit is complete and `story_health` passes (`shape_order_bind.resolve_air_order`). Otherwise ranking wins.


## Degradation ladder

`complete` → `degraded` → `forced_sparse` → `absent_legacy`. G1 always reachable.

## Multilingual

VO script language matches source (or operator language policy). No English-default documentary bridges on non-English tape.
