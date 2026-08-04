# Mastering prompts

Contracts for the Unified Mastering Process. Canon: [../../cross-cutting/mastering-process.md](../../cross-cutting/mastering-process.md).

Runtime (future): prepend `_shared/analysis-preamble.system.txt` when wired into `llm_runner`. Until cutover these are **spec contracts**.

| File | Role | Tier hint |
|------|------|-----------|
| `prompt-mint.system.txt` | Mint field/step system prompts | economy |
| `prompt-edit.system.txt` | Rewrite weak/checklist framing | economy |
| `clarify-triage.system.txt` | Auto-resolve clarifying Qs from artifacts | economy |
| `shape-meta-architect.system.txt` | L0 per-podcast agenda | flagship |
| `shape-l1-horizon.system.txt` | L1 seed | economy |
| `shape-l2-candidates.system.txt` | L2 seed | standard |
| `shape-l3-deep-dive.system.txt` | L3 seed | standard |
| `shape-l4-cross-critique.system.txt` | L4 excellence filter | standard/flagship |
| `shape-l5-convergence.system.txt` | L5 seed | standard |
| `capability-cold-open.system.txt` | Cold-open module seed | standard |
| `flagship-synthesize.system.txt` | Authoritative mastering_plan | flagship |
| `polish-audit.system.txt` | Audio-grounded post-mix polish + bounded remux (heritage; OH-P1 dropped) | flagship |
| `junction-feel-audit.system.txt` | Single post-mix feel audit of junctions (`OH-J1`) — never per-edge | standard |

North-star pillars must appear in every shape-related mint/edit.

## Quality hardening

Canon: [../../cross-cutting/mastering-quality-hardening.md](../../cross-cutting/mastering-quality-hardening.md).

| File | Role | Tier hint |
|------|------|-----------|
| `research-router.system.txt` | Route the 38 fields for this source | economy |
| `eval-rubric-mint.system.txt` | Per-run style rubric (with L0) | flagship |
| `semantic-integrity.system.txt` | Confirm/clear fabrication flags | standard |

### L4 critic panel

Six independent critics, then a flagship arbiter. Spec: [../../cross-cutting/mastering-multi-critic.md](../../cross-cutting/mastering-multi-critic.md).

| File | `critic_id` | Hard-fail |
|------|-------------|-----------|
| `critics/narrative-editor.system.txt` | `narrative_editor` | no |
| `critics/engagement-listener.system.txt` | `engagement_listener` | no |
| `critics/audio-intelligibility.system.txt` | `audio_intelligibility` | no |
| `critics/integrity.system.txt` | `integrity` | **yes** |
| `critics/pacing-repetition.system.txt` | `pacing_repetition` | no |
| `critics/style-fit.system.txt` | `style_fit` | no |
| `critics/l4-arbiter.system.txt` | arbiter (flagship) | enforces kills |

Every critic scores against `mastering/shape/eval_rubric.json` and must cite `evidence_refs`.
