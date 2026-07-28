# Local Audio Probe Platform + Vernacular Evidence Covenant

**Status:** Implemented (heuristic fail-open path; MLX listen-and-answer certification optional).

**North star:** one interview → `master/master.wav` with in-flow vernacular and other audio judgments preserved as golden facts.

## What it does

After `transcribe`, stage `audio_probe_build`:

1. Builds uninterrupted **speaker flows** (all speakers).
2. Runs short **system-prompt probes** (spoken warm-up design; currently heuristic answers when MLX interrogate is unset).
3. Writes `analysis/run_golden_facts.json`, `transcript/protected_zones.json`, `transcript/speaker_flows.json`, `vernacular/probe_report.json`.

After segments exist, `vernacular_segment_sanitize` performs **N-way** parent→child splits for any alternation pattern (`EN|SW|EN|SW|EN`, …), tags special children, and records `vernacular/resplit_report.json`.

## Probe packs

Prompts: [`docs/prompts/audio_probes/`](../prompts/audio_probes/). Registry: `src/interview_mux/audio_probe_registry.py`.

| Pack | Examples | Gate |
|---|---|---|
| vernacular | multilingual_or_uncommon, keywords, spans | hard must_keep (when `enforcement_mode=authoritative`) |
| salience | passion, pull_quote, affect | soft prefer |
| structure | speech_act | advisory |
| defect | crosstalk, bleed, unintelligible, discontinuity | advisory |
| entities | name_or_title | advisory |
| safety | sensitive_disclosure | safety |
| narrative / fidelity | payoff, disagreement, retelling, nonliteral | soft/advisory |

## Config

`audio_probes.*` and `local_speech.interrogate_*` — see [config-keys.md](./config-keys.md).

Default `enforcement_mode` is `shadow` (facts written; auto_pack does not hard-block until `authoritative`).

## Consumers

- `transcript_quality_for_ctx` injects golden facts + protected zone summary into LLM stage inputs.
- `selection_auto_pack._arc_critical_ids` unions authoritative vernacular must_keep segment ids.
- Analysis preamble: treat golden facts as binding evidence when present.

## Related

- Broader same-language mastering: [multilingual-support.md](./multilingual-support.md)
- Segment lineage / NLE splits: [segment-lineage.md](./segment-lineage.md)
