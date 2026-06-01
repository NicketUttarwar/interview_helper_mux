# Assembly and mux

Combine speech, interviewer VO pickup, transitions, and ElevenLabs SFX into `assembly.wav`, then master export.

**North star:** [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md)

## Mix engine (BUILD-065, shipped)

Module: `src/interview_mux/sound_design.py` — `mix_flow1` / `mix_flow2`.

| Stage | Pipeline id | Output |
|-------|-------------|--------|
| Flow 1 mix | **`mix_flow1`** (canonical) | `flow_1_master/assembly.wav` — EDL speech + VO + SDP overlays (beds, stingers, ducking) |
| Flow 2 mix | **`mix_flow2`** (canonical) | `flow_2_highlights/assembly.wav` — highlights + cold open + shared `between_clips` transition |
| Legacy alias | `mux_flow1` / `mux_flow2` | Same artifact; **single-stage rerun only** — not in `FLOW1_ORDER` / `FLOW2_ORDER` |

`master_flow*` loudness-normalizes `assembly.wav` → `master.wav` (SFX remain audible).

**Listen check:** After `mix_flow1` / `master_flow1`, confirm beds/stingers in `master.wav`.

## Assembly wiring (BUILD-067–069)

| Ticket | Behavior |
|--------|----------|
| BUILD-067 | **Shipped:** `edl.json` includes `vo_pickup`, gap `placement`, transition anchors |
| BUILD-068 | **Shipped:** `segments/nle_edits.json` → `selection.json` + EDL segment bounds |
| BUILD-069 | **Shipped:** `assembly_preview.wav` — speech + VO only, before ElevenLabs spend |

Stage ids and mix tables: [stage-registry.md](../../build-out/stage-registry.md) · [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md).

## Sound design inputs (BUILD-060–064)

See [sound-design.md](../../cross-cutting/sound-design.md).

- `understanding/sound_design_plan.json` — palettes, reusable `assets`, per-flow `cues`
- `sound_design/assets/{asset_id}.wav` — one file per asset, many cue references
- Legacy fallback: `flow_*/sfx/*.wav` when SDP cues absent (Flow 1 bed + index stingers)

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

**ffmpeg**, **pydub**, **ElevenLabs REST** `POST /v1/music` Music v2 (`elevenlabs_rest.py`) — [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md) · [elevenlabs-integration-guide.md](../../cross-cutting/elevenlabs-integration-guide.md)

**QA (Flow 1):**

```bash
python tools/verify_edl.py --run-id <exec_id>
python tools/validate_narrative.py --run-id <exec_id> [--require-selection]
```

## Modules

- `sound_design.py` — mix engine (`mix_flow1`, `mix_flow2`)
- `assembly_flow1.py` — `edl_flow1`, `run_mux` → `mix_flow1`, `assembly_preview`
- `assembly_flow2.py` — `run_micro_assembly` → `mix_flow2`
- `sfx_elevenlabs.py`, `sound_design_stages.py`

---

## Build-out

BUILD-035, BUILD-043, BUILD-065–066 · [README.md](../../build-out/README.md) · [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md)
