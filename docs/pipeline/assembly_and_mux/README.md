# Assembly and mux

Combine speech, interviewer VO pickup, transitions, and MMAudio SFX into `assembly.wav`, then master export.

**North star:** [podcast-quality-roadmap.md](../../cross-cutting/podcast-quality-roadmap.md) · single delivery path (Flow 2 mix removed — [drop-manifest](../../v2/drop-manifest.md))

## Mix engine (BUILD-065, shipped)

Module: `src/interview_mux/sound_design.py` — canonical stage id **`mix`**.

| Stage | Pipeline id | Output |
|-------|-------------|--------|
| Mix | **`mix`** | `master/assembly.wav` — EDL speech + VO + SDP overlays (beds, stingers, ducking) |
| Junction QA | **`junction_snip_qa`** | Repairs mid-thought chops / VO micros before master |
| Legacy alias | `mux_flow1` | Same mix artifact; **single-stage rerun only** — not in `DELIVERY_ORDER` |

`master_finalize` loudness-normalizes `assembly.wav` → `master/master.wav` (SFX remain audible).

**Listen check:** After `mix` / `junction_snip_qa` / `master_finalize`, confirm beds/stingers in `master.wav`.

## Assembly wiring (BUILD-067–069)

| Ticket | Behavior |
|--------|----------|
| BUILD-067 | **Shipped:** `edl.json` includes `vo_pickup`, gap `placement`, transition anchors |
| BUILD-068 | **Shipped:** `segments/nle_edits.json` → `selection.json` + EDL segment bounds |
| BUILD-069 | **Shipped:** `assembly_preview.wav` — speech + VO only, before MMAudio SFX generation |
| EDL narrative QC | **Shipped:** `edl_narrative_audit` + `edl_narrative_qc` verify final EDL narrative semantics before write |

Stage ids: [stage-contracts/00-INDEX.md](../../cross-cutting/stage-contracts/00-INDEX.md) · [port-manifest.csv](../../v2/port-manifest.csv).

## Sound design inputs (BUILD-060–064)

See [sound-design.md](../../cross-cutting/sound-design.md).

- `understanding/sound_design_plan.json` — palettes, reusable `assets`, `flow_plans.podcast.cues`
- `sound_design/assets/{asset_id}.wav` — one file per asset, many cue references

**Pre-clean before mix:** Operator may accept full-source or `normalized_rebuild` clean offer immediately before mux — see [audio_preclean](../audio_preclean/README.md).

## Heritage

`REMOVED_mix_flow2` / `REMOVED_assembly_flow2.py` / `REMOVED_flow2/` were deleted with Flow 2. Do not document them as live paths.
