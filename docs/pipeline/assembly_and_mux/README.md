# Assembly and mux

Combine speech, interviewer VO pickup, transitions, and ElevenLabs SFX into `assembly.wav`, then master export.

**North star:** [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md)

## v1 (shipped) — known gaps

| Flow | Tickets | Behavior |
|------|---------|----------|
| Flow 1 | BUILD-033–035 | Brief + `sfx/*.wav` generated; mux is **speech-only** concat — VO, transitions, SFX **not mixed** |
| Flow 2 | BUILD-041–043 | Clips + `sfx_NNN` by **index** (cold open / shared transition semantics wrong) |

Do not tell operators that v1 `master.wav` is the final podcast mix.

## Planned — assembly wiring (BUILD-067–069)

| Ticket | Behavior |
|--------|----------|
| BUILD-067 | `edl.json` includes `vo_pickup`, gap `placement`, transition ordering |
| BUILD-068 | `segments/nle_edits.json` → manifest / `selection.json` |
| BUILD-069 | `assembly_preview.wav` — speech + VO only, before ElevenLabs spend |

## Planned — coherent mix (BUILD-060–066)

See [sound-design.md](../../cross-cutting/sound-design.md).

- `understanding/sound_design_plan.json` — palettes, reusable `assets`, per-flow `cues`
- `sound_design/assets/{asset_id}.wav` — one file per asset, many cue references
- `mix_flow1` / `mix_flow2` — pydub overlay (beds), ducked under speech, VO bridges

**Pre-clean before mix:** Operator may accept full-source or `normalized_rebuild` clean offer immediately before mux — see [audio_preclean](../audio_preclean/README.md).

## Flow 1

| Ticket | Artifact |
|--------|----------|
| BUILD-033 | `podcast_sfx_brief.json` (v1 legacy) |
| BUILD-062 | SDP `flow_plans.flow1` |
| BUILD-034 / BUILD-064 | generated assets |
| BUILD-035 / BUILD-065 | `assembly.wav` with VO + beds + stingers |
| BUILD-069 | `assembly_preview.wav` |

## Flow 2

| Ticket | Artifact |
|--------|----------|
| BUILD-041 | `sfx_brief.json` (v1 legacy) |
| BUILD-063 | SDP `flow_plans.flow2` |
| BUILD-042 / BUILD-064 | generated assets |
| BUILD-043 / BUILD-065 | `assembly.wav` — cold open, shared `between_clips` transition |

## Tools

ffmpeg, pydub, ElevenLabs REST `POST /v1/sound-generation` (`elevenlabs_rest.py`)

## Modules

**v1:** `assembly_flow1.py`, `assembly_flow2.py`, `sfx_elevenlabs.py`

**planned:** `sound_design.py`, `stages/sound_design_stages.py`
