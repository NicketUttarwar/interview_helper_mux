# Assembly and mux

Combine speech, interviewer VO pickup, transitions, and MMAudio SFX into `assembly.wav`, then master export.

**North star:** [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md)

## Mix engine (BUILD-065, shipped)

Module: `src/interview_mux/sound_design.py` — `mix` / `REMOVED_mix_flow2`.

| Stage | Pipeline id | Output |
|-------|-------------|--------|
| Flow 1 mix | **`mix`** (canonical) | `master/assembly.wav` — EDL speech + VO + SDP overlays (beds, stingers, ducking) |
| Flow 2 mix | **`REMOVED_mix_flow2`** (canonical) | `REMOVED_flow2/assembly.wav` — highlights + cold open + shared `between_clips` transition |
| Legacy alias | `mux_flow1` / `mux_flow2` | Same artifact; **single-stage rerun only** — not in `DELIVERY_ORDER` / `REMOVED_FLOW2_ORDER` |

`master_flow*` loudness-normalizes `assembly.wav` → `master.wav` (SFX remain audible).

**Listen check:** After `mix` / `master_finalize`, confirm beds/stingers in `master.wav`.

## Assembly wiring (BUILD-067–069)

| Ticket | Behavior |
|--------|----------|
| BUILD-067 | **Shipped:** `edl.json` includes `vo_pickup`, gap `placement`, transition anchors |
| BUILD-068 | **Shipped:** `segments/nle_edits.json` → `selection.json` + EDL segment bounds |
| BUILD-069 | **Shipped:** `assembly_preview.wav` — speech + VO only, before MMAudio SFX generation |
| EDL narrative QC | **Shipped:** `edl_narrative_audit` + `edl_narrative_qc` verify final EDL narrative semantics before write |

Stage ids and mix tables: [stage-contracts/00-INDEX.md](../../cross-cutting/stage-contracts/00-INDEX.md) · [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md).

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
| BUILD-062 | SDP `flow_plans.podcast` |
| BUILD-034 / BUILD-064 | generated assets |
| BUILD-035 / BUILD-065 | `assembly.wav` with VO + beds + stingers |
| BUILD-069 | `assembly_preview.wav` |

## Flow 2

| Ticket | Artifact |
|--------|----------|
| BUILD-041 | `sfx_brief.json` (v1 legacy) |
| BUILD-063 | SDP `REMOVED_flow_plans_flow2` |
| BUILD-042 / BUILD-064 | generated assets |
| BUILD-043 / BUILD-065 | `assembly.wav` — cold open, shared `between_clips` transition |

## Tools

**ffmpeg**, **pydub**, **local MMAudio** `POST /v1/music` Music v2 (`maudio_runner.py`) — [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md) · [local-audio-stack.md](../../cross-cutting/local-audio-stack.md)

**QA (Flow 1):**

```bash
python tools/verify_edl.py --run-id <exec_id>                         # schema only
python tools/validate_edl.py --run-id <exec_id>                       # timeline/mechanical QC
python tools/validate_narrative.py --run-id <exec_id> --include-edl   # upstream + EDL narrative QC
```

## Modules

- `sound_design.py` — mix engine (`mix`, `REMOVED_mix_flow2`)
- `assembly.py` — `edl`, `run_mux` → `mix`, `assembly_preview`
- `edl_narrative_qc.py` — final EDL narrative semantics
- `stages/edl_narrative_audit.py` — local-volley + flagship semantic audit before EDL
- `REMOVED_assembly_flow2.py` — `run_micro_assembly` → `REMOVED_mix_flow2`
- `sfx_mmaudio.py`, `sound_design_stages.py`
