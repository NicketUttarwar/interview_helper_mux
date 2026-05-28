# G1.5 + Value-Analysis — execution guide (remaining work)

**Purpose:** Track **optional** follow-ups only. Core G1.5 wiring and value-analysis tooling are **shipped** on this branch.

**Constraints (unchanged):**
- Do **not** add value-analysis stages to default [`pipeline.py`](../../src/interview_mux/pipeline.py) order.
- G1.5: `g1_5_require_prompt_approval` (default `false`).
- Value-analysis: `value_analysis.*` (default all off).

**Enable locally:** set `g1_5_require_prompt_approval: true` and/or `value_analysis.enabled: true` in `config/app.defaults.json` (or secrets overlay).

---

## Your execution list (remaining)

| Command | Status | Action |
|---------|--------|--------|
| **A5** — Post-listen log hook | Not built | Optional API: `POST …/elevenlabs-prompts/listen-result` |
| **B5** — GUI value_features panel | Not built | Optional read-only panel on `content_context` when `value_analysis.enabled` |

Everything else from the original guide is **done** — see [Shipped checklist](#shipped-checklist) below.

**Suggested order:** A5 and/or B5 only if you need them; skip otherwise.

---

## Architecture (shipped)

```mermaid
flowchart TB
  subgraph g15 [Track A G1.5 — shipped]
    CFG1[g1_5_require_prompt_approval]
    API[GET PUT POST elevenlabs-prompts]
    GUI[app.js review panel]
    PREFLIGHT[can_run_elevenlabs_generation]
    SFX[sfx_elevenlabs.run_sfx_generation]
    CFG1 --> API
    API --> GUI
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
    CFG2 --> SPIKE
    CFG2 --> TR
    CFG2 --> AU
    SPIKE --> CLI1
    TR --> CLI2
    AU --> CLI2
  end
```

---

## Command A5 (optional) — Post-listen log hook

**Agent prompt:**

```text
Optional G1.5 post-listen hook — small API only.

Add POST /api/runs/{run_id}/elevenlabs-prompts/listen-result
Body: { asset_id, result: "pass"|"fail", note?: string }
Append to run_meta.elevenlabs_listen_results[] and ctx.log elevenlabs_post_listen_pass or elevenlabs_post_listen_fail.

No GUI required in this command.
```

**Skip if time-boxed.**

---

## Command B5 (optional) — GUI debug panel

**Agent prompt:**

```text
Optional: when value_analysis.enabled, show read-only summary of understanding/value_features.json on content_context stage in app.js (fetch artifact API). If file missing, hint to run tools/extract_value_features.py.

Only if config flag on. No pipeline changes.
```

**Skip if CLI-only is enough.**

---

## Shipped checklist

### Track A — G1.5 (complete)

| File | Role |
|------|------|
| `src/interview_mux/g15_prompt_review.py` | Gate + validation + SDP warnings |
| `src/interview_mux/stages/sfx_elevenlabs.py` | Calls `require_elevenlabs_generation` |
| `src/interview_mux/web/runner.py` | Pre-flight before SFX stages |
| `src/interview_mux/web/server.py` | GET/PUT/POST hardened (`warnings`, schema on PUT) |
| `src/interview_mux/web/static/app.js` | Review panel (`prompt_influence`, warnings, approve gate, SFX block) |
| Docs | `operator-gates.md`, `gui-surface-map.md`, checklists, troubleshooting, `sound-design.md`, guardrails |

### Track B — Value-analysis (complete)

| File | Role |
|------|------|
| `config/app.defaults.json` + template | `value_analysis` block |
| `src/interview_mux/value_analysis/config.py` | `value_analysis_enabled`, `value_analysis_flag` |
| `src/interview_mux/value_analysis/spike_score.py` | Rubric aggregation |
| `src/interview_mux/value_analysis/features_transcript.py` | Transcript metrics |
| `src/interview_mux/value_analysis/features_audio.py` | Audio metrics |
| `tools/run_value_spike.py` | Spike CLI |
| `tools/extract_value_features.py` | Features CLI |
| `docs/cross-cutting/json-schemas/value_features.schema.json` | Artifact shape |
| `tests/fixtures/value_analysis/spike_flow1_sound.json` | Example scorecard |
| Docs | `value-analysis/README.md`, `future-proofing.md`, `flow1-sound-and-mix.md`, `spike-results-and-winners.md` (fixture row) |

### Config keys

| Key | Default | Effect |
|-----|---------|--------|
| `g1_5_require_prompt_approval` | `false` | When `true`, block ElevenLabs SFX until GUI approve |
| `value_analysis.enabled` | `false` | Master switch for VA tools |
| `value_analysis.spike_scoring` | `true` | Allow `run_value_spike.py` when enabled |
| `value_analysis.transcript_features` | `true` | Transcript profile in extractor |
| `value_analysis.audio_features` | `false` | Audio profile in extractor |

Documented in [config-keys.md](../cross-cutting/config-keys.md).

---

## Out of scope (this guide)

- Pytest / CI coverage (later)
- Default pipeline stages for value-analysis
- CLAP / SSL / new ML dependencies
- Post-listen GUI (unless A5 is built)

---

## Related

- [steps-forward.md](./steps-forward.md) — main build-out backlog  
- [value-analysis/README.md](../pipeline/value-analysis/README.md) — rubrics and tooling flags  
- [elevenlabs-integration-guide.md](../cross-cutting/elevenlabs-integration-guide.md) — G1.5 operator journey  
