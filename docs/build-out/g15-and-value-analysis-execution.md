# G1.5 + Value-Analysis — execution guide

**Purpose:** Track **optional** follow-ups only. Core G1.5 wiring and value-analysis tooling are **shipped** on this branch.

**Constraints (unchanged):**
- Do **not** add value-analysis stages to default [`pipeline.py`](../../src/interview_mux/pipeline.py) order.
- Shipped defaults in `config/app.defaults.json`: `g1_5_require_prompt_approval: true`, `value_analysis.enabled: true`, `value_analysis.auto_extract_after_content_context: true`.

**Disable locally:** set flags to `false` in `config/app.defaults.json` (or secrets overlay).

**GUI:** React SPA in [`frontend/`](../../frontend/) (Vite → `src/interview_mux/web/static/`). Legacy `app.js` references in historical docs are superseded.

---

## Your execution list (remaining)

| Command | Status | Action |
|---------|--------|--------|
| **A5** — Post-listen log hook | **Shipped** | `POST /api/runs/{run_id}/elevenlabs-prompts/listen-result` → `run_meta.elevenlabs_listen_results[]` |
| **B5** — GUI value_features panel | **Shipped** | [`frontend/src/components/gates/ValueFeaturesPanel.tsx`](../../frontend/src/components/gates/ValueFeaturesPanel.tsx) on `content_context` when `value_analysis.enabled` |
| **Command 5** — Post-listen GUI | **Shipped** | [`frontend/src/components/gates/ElevenLabsPostListenPanel.tsx`](../../frontend/src/components/gates/ElevenLabsPostListenPanel.tsx) on craft + SFX stages |

Everything else from the original guide is **done** — see [Shipped checklist](#shipped-checklist) below.

---

## Architecture (shipped)

```mermaid
flowchart TB
  subgraph g15 [Track A G1.5 — shipped]
    CFG1[g1_5_require_prompt_approval]
    API[GET PUT POST elevenlabs-prompts]
    LISTEN[POST listen-result + post-listen GUI]
    GUI[React craft + SFX panels]
    PREFLIGHT[can_run_elevenlabs_generation]
    SFX[sfx_elevenlabs.run_sfx_generation]
    CFG1 --> API
    API --> GUI
    LISTEN --> GUI
    PREFLIGHT --> SFX
    API --> PREFLIGHT
  end
  subgraph va [Track B Value-analysis — shipped]
    CFG2[value_analysis.enabled + sub-flags]
    SPIKE[spike_score.py]
    TR[features_transcript.py]
    AU[features_audio.py]
    CLI1[tools/run_value_spike.py]
    CLI2[tools/extract_value_features.py]
    PANEL[ValueFeaturesPanel.tsx]
    CFG2 --> SPIKE
    CFG2 --> TR
    CFG2 --> AU
    CFG2 --> PANEL
    SPIKE --> CLI1
    TR --> CLI2
    AU --> CLI2
  end
```

---

## Shipped checklist

### Track A — G1.5 (complete)

| File | Role |
|------|------|
| `src/interview_mux/g15_prompt_review.py` | Gate + validation + SDP warnings |
| `src/interview_mux/stages/sfx_elevenlabs.py` | Calls `require_elevenlabs_generation` |
| `src/interview_mux/web/runner.py` | Pre-flight before SFX stages |
| `src/interview_mux/web/server.py` | GET/PUT/POST hardened (`warnings`, schema on PUT); **POST listen-result** |
| `frontend/src/components/gates/ElevenLabsPromptReviewPanel.tsx` | Craft review panel |
| `frontend/src/components/gates/ElevenLabsPostListenPanel.tsx` | Post-listen Pass/Fail on craft + SFX stages |
| `frontend/src/components/gates/ElevenLabsBlockedPanel.tsx` | G1.5 blocked state CTA |
| Docs | `operator-gates.md`, `gui-surface-map.md`, checklists, troubleshooting, `sound-design.md`, guardrails |

### Track B — Value-analysis (complete)

| File | Role |
|------|------|
| `config/app.defaults.json` + template | `value_analysis` block (defaults on) |
| `src/interview_mux/value_analysis/config.py` | `value_analysis_enabled`, `value_analysis_flag` |
| `src/interview_mux/value_analysis/spike_score.py` | Rubric aggregation |
| `src/interview_mux/value_analysis/features_transcript.py` | Transcript metrics |
| `src/interview_mux/value_analysis/features_audio.py` | Audio metrics |
| `tools/run_value_spike.py` | Spike CLI |
| `tools/extract_value_features.py` | Features CLI |
| `src/interview_mux/value_analysis/extract.py` | Shared extract + post-`content_context` hook |
| `frontend/src/components/gates/ValueFeaturesPanel.tsx` | Read-only panel on `content_context` when enabled |
| `docs/cross-cutting/json-schemas/value_features.schema.json` | Artifact shape |
| `tests/fixtures/value_analysis/spike_flow1_sound.json` | Example scorecard |
| Docs | `value-analysis/README.md`, `future-proofing.md`, `flow1-sound-and-mix.md`, `spike-results-and-winners.md` |

### Config keys

| Key | Default | Effect |
|-----|---------|--------|
| `g1_5_require_prompt_approval` | `true` | When `true`, block ElevenLabs SFX until GUI approve |
| `value_analysis.enabled` | `true` | Master switch for VA tools + GUI panel |
| `value_analysis.spike_scoring` | `true` | Allow `run_value_spike.py` when enabled |
| `value_analysis.transcript_features` | `true` | Transcript profile in extractor |
| `value_analysis.audio_features` | `true` | Audio profile in extractor |
| `value_analysis.auto_extract_after_content_context` | `true` | After successful `content_context`, auto-write `understanding/value_features.json` |

Documented in [config-keys.md](../cross-cutting/config-keys.md).

---

## Out of scope (this guide)

- Default pipeline stages for value-analysis moonshots
- CLAP / SSL / new ML dependencies (see [remaining-build-commands.md](./remaining-build-commands.md) Command 8)

---

## Related

- [remaining-build-commands.md](./remaining-build-commands.md) — optional R&D queue
- [value-analysis/README.md](../pipeline/value-analysis/README.md) — rubrics and tooling flags
- [elevenlabs-integration-guide.md](../cross-cutting/elevenlabs-integration-guide.md) — G1.5 operator journey
