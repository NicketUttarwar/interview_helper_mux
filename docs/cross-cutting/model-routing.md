# Model routing

**SDK / runtime:** `openai` package version — [anchored-toolchain.md](./anchored-toolchain.md#python-packages-application). Use **Context7** at that version when changing `llm_runner.py`.

OpenAI Chat Completions models per pipeline stage. **Prose in this repo uses tier names** (`economy`, `standard`, `flagship`), not scattered API IDs.

**Status:** Tier matrix and arbiter orchestration are **spec only** — see [llm-orchestration.md](./llm-orchestration.md). v1 runtime resolves a single model string per `stage_key` from `config/app.defaults.json` via `get_model()`.

**Related:**

- [llm-stage-model-matrix.md](./llm-stage-model-matrix.md) — per-stage severity, tier, decompose rules
- [config-keys.md](./config-keys.md) — config shape (current + proposed)
- [llm-orchestration-implementation-handoff.md](./llm-orchestration-implementation-handoff.md)

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
| flagship | `gpt-4o` (upgrade to newest flagship when available) | 2026-05-27 |

Optional secrets overrides (proposed, not implemented): `OPENAI_TIER_ECONOMY`, `OPENAI_TIER_STANDARD`, `OPENAI_TIER_FLAGSHIP`.

---

## Per-stage default tiers (target)

Full matrix: [llm-stage-model-matrix.md](./llm-stage-model-matrix.md).

| Stage key | Default tier | Severity |
|-----------|--------------|----------|
| `speaker_roles` | economy | low |
| `content_context` | economy | medium |
| `boundary_detection` | standard | medium |
| `segment_classification` | standard | medium |
| `missing_framing` | flagship | high |
| `optimal_questions` | flagship | high |
| `topic_coverage_audit` | flagship | high |
| `narrative_arc_plan` | flagship | high |
| `full_master_ranking` | flagship | high |
| `highlight_selection` | flagship | high |
| `podcast_show_description` | flagship | high |
| `transitions` | economy | low |
| `podcast_sfx_brief` | economy | low |
| `sfx_brief` | economy | low |

Planned sound-design stages: economy for `sound_design_palettes` and `elevenlabs_prompt_craft`; flagship for `sound_design_plan_flow1` / `flow2` — [sound-design.md](./sound-design.md).

---

## v1 runtime (`config/app.defaults.json`)

Today each `models.<stage_key>` is a **flat API ID string**. Committed defaults (approximate tier mapping):

| Stage key | v1 API ID (committed) | Maps to tier |
|-----------|----------------------|--------------|
| `speaker_roles`, `content_context`, `transitions`, `podcast_sfx_brief`, `sfx_brief` | economy registry ID | economy |
| `boundary_detection`, `segment_classification`, `missing_framing`, `optimal_questions`, Flow 1/2 selection stages | standard registry ID | standard / flagship per matrix above |

**Target:** high-severity stages should use **flagship** registry ID once smart routing is implemented; v1 may still point some high-severity stages at standard IDs until config is migrated.

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
- Flow 2 highlight selection
- Flow 3 podcast show description (`podcast_show_description`)
- Planned sound-design plan stages

Keep **economy** for speaker/content pass, transitions, SFX briefs, ElevenLabs prompt craft, and all **arbiter** / **shard** sub-calls.

Use **standard** for segmentation cascade (boundaries → classification) unless arbiter requests upgrade or decompose.
