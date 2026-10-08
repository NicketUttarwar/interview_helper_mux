# Model routing

**SDK / runtime:** `openai` package version — [anchored-toolchain.md](./anchored-toolchain.md#python-packages-application). Use **Context7** at that version when changing `llm_runner.py`.

OpenAI Chat Completions models per pipeline stage. **Prose in this repo uses tier names** (`economy`, `standard`, `flagship`), not scattered API IDs.

**Status:** BUILD-073 ships tier-aware routing in runtime (`model_registry.resolve_model`) for `primary`, `arbiter`, `shard`, and `collate` task kinds. Stage-level string overrides in `config/app.defaults.json` remain an escape hatch.

**Related:**

- [llm-stage-model-matrix.md](./llm-stage-model-matrix.md) — per-stage severity, tier, decompose rules
- [config-keys.md](./config-keys.md) — config shape (runtime + secrets)
- [llm-call-record-framework.md](./llm-call-record-framework.md) — call records and audit trail

---

## Tier vocabulary

| Tier | Role | Typical use |
|------|------|-------------|
| **economy** | Lowest cost | Speaker roles, SFX briefs, transitions, arbiter, shard sub-calls |
| **standard** | Cascade-sensitive mid tier | Boundary detection, segment classification |
| **flagship** | Highest editorial impact | Gaps, optimal questions, Flow 1/2 selection and narrative planning |

Do **not** pin flagship to a marketing name in pipeline READMEs — use the tier and update the registry below when OpenAI ships newer models.

---

## Model tier registry

**Only this subsection should list concrete OpenAI API model IDs.** Update `last_verified` when operators confirm IDs against their account.

| Tier | Recommended API ID | `last_verified` |
|------|-------------------|-----------------|
| economy | `gpt-4o-mini` | 2026-05-27 |
| standard | `gpt-4o` | 2026-05-27 |
| flagship | `gpt-5.6-terra` (1.05M input context) | 2026-08-11 |

Optional secrets overrides: `OPENAI_TIER_ECONOMY`, `OPENAI_TIER_STANDARD`, `OPENAI_TIER_FLAGSHIP` (read from merged config `secrets` via `model_registry`).

---

## Per-stage default tiers (target)

Full matrix: [llm-stage-model-matrix.md](./llm-stage-model-matrix.md).

| Stage key | Default tier | Severity |
|-----------|--------------|----------|
| `speaker_roles` | flagship | low |
| `content_context` | flagship | medium |
| `boundary_detection` | flagship | medium |
| `segment_classification` | flagship | medium |
| `sound_design_palettes` | flagship | low |
| `missing_framing` | flagship | high |
| `optimal_questions` | flagship | high |
| `topic_coverage_audit` | flagship | high |
| `narrative_arc_plan` | flagship | high |
| `full_master_ranking` | flagship | high |
| `edl_narrative_audit` | flagship | high |
| `REMOVED_highlight_selection` | flagship | high |
| `REMOVED_podcast_show_description` | flagship | high |
| `transitions` | flagship | low |
| `podcast_sfx_brief` | flagship | low |
| `sfx_brief` | flagship | low |
| `sound_design_plan` | flagship | high |
| `REMOVED_sdp_flow2` | flagship | high |
| `sfx_prompt_craft` | flagship | low |
| `episode_meta_build` | flagship | medium |
| `episode_cover_prompt_craft` | flagship | medium |
| `episode_cover_vision_pick` | flagship | medium |

Episode covers also call OpenAI **Images** (`podcast.cover_image.model`, pinned `gpt-image-2`, `quality=high`, 3 candidates) — not chat tier routing. See [podcast-cover-theme.md](./podcast-cover-theme.md).


Sound-design stage details: [sound-design.md](./sound-design.md).

---

## Runtime (`config/app.defaults.json`)

Runtime supports both:

- `models.tiers` + `models.stages.<stage_key>.tier` (preferred)
- `models.<stage_key>` flat API ID string override (escape hatch)

Committed defaults still include flat stage strings for backward compatibility.

| Stage key | v1 API ID (committed) | Maps to tier |
|-----------|----------------------|--------------|
| All stages in `STAGE_ARTIFACT_SCHEMAS` (understanding, segmentation, gaps, flow JSON) | flagship registry ID (`gpt-5.6-terra`) | flagship |
| `arbiter`, `shard` sub-calls | economy registry ID | economy |

See `models.stages.*.tier` in committed `config/app.defaults.json`. Artifact generation spec: [artifact-generation-and-validation.md](./artifact-generation-and-validation.md).

**Context-window ladder (every OpenAI chat call):** configured tier → one flagship retry on `context_length` → one safe-prune pack + one flagship retry. See [truncation-integrity.md](./truncation-integrity.md) (`analysis.safe_pruning`).

**Note:** Prefer `models.stages.<key>.tier` for routing. Flat `models.<stage_key>` string overrides remain an escape hatch; `retry_uptier` bypasses flat overrides so tier bumps take effect.

Override per machine in `config/app.defaults.json` — never in prompt files.

---

## Config drift

`config/templates/app.defaults.json` may differ from committed `config/app.defaults.json` (e.g. segmentation stages on economy in the template). **Trust committed `app.defaults.json` for runtime** until templates are aligned in a separate config PR. This docs track does not edit `config/`.

---

## Overrides (proposed)

```json
"models": {
  "tiers": { "economy": "...", "standard": "...", "flagship": "..." },
  "stages": {
    "missing_framing": { "tier": "flagship", "severity": "high" }
  },
  "missing_framing": "gpt-4o"
}
```

If `models.<stage_key>` is a string, it wins as an explicit API ID escape hatch. See [config-keys.md](./config-keys.md).

---

## When to use flagship

Default **flagship** on first pass for:

- Gap detection (`missing_framing`) and optimal questions
- Flow 1 coverage audit, narrative plan, full master ranking
- Flow 1 EDL narrative audit (`edl_narrative_audit`)
- Flow 2 highlight selection
- Flow 3 podcast show description (`REMOVED_podcast_show_description`)
- Sound-design plan stages (`sound_design_plan`, `REMOVED_sdp_flow2`)

Keep **economy** for speaker/content pass, transitions, SFX briefs, MMAudio SFX prompt craft, and all **arbiter** / **shard** sub-calls.

Use **standard** for segmentation cascade (boundaries → classification) unless arbiter requests upgrade or decompose.
