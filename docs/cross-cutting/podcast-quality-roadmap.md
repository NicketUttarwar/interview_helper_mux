# Podcast quality roadmap

**Dependencies:** Pinned stack for mix/SFX/STT — [anchored-toolchain.md](./anchored-toolchain.md).

How the project moves from **strong analysis** to a **polished mastered podcast** the operator can trust. This doc is the north star for docs, build-out tickets, and GUI copy — not a promise that every item is implemented yet.

## v1 reality vs target

| Layer | v1 (shipped) | Target |
|-------|--------------|--------|
| Analysis | Content brief, segments, gaps, Flow 1 ranking; profile gate before extended Flow 1 (BUILD-081); **narrative QC** (`validate_narrative.py`) | Same pattern as validators expand |
| VO pickup (G1) | Record lines to `vo_pickup/`; optional **pickup-scoped pre-clean** (`vo_pickup` scope, BUILD-019 + BUILD-072) | Same |
| Assembly Flow 1 | EDL with gaps + VO + transitions; **`assembly_preview.wav`** before SFX; **`mix`** (speech + VO + SDP beds/stingers); narrative QC warn/block before ranking + EDL; **extended EDL narrative QC** after flagship `edl_narrative_audit` | Deeper operator edit UX |
| Assembly Flow 2 | **`REMOVED_mix_flow2`** montage + shared transition assets via SDP | Cold-open polish refinements |
| Flow 3 publishing | Third-person show description JSON + markdown (BUILD-045–046, 080) | Same |
| SFX | SDP + **`sfx_prompt_craft`** + one WAV per `asset_id`; G1.5 optional approve gate; **soundscape_policy** cue slots + verify→remux (BUILD-SS) | Deeper craft iteration loops |
| NLE GUI | Mouse-first editor: smart presets, review queue, filters, undo history, transcript selection trim, partial apply modes (`trim_only` / `structural` / `full_refresh`), assembly A/B preview; feeds ranking + EDL (BUILD-068) | Extended listen-study metrics + deeper craft loops |
| Master QA | LUFS + true peak (`verify_master`, BUILD-070–071); narrative QC (`validate_narrative`, topic + chapter checks); EDL timeline QC (`validate_edl`); extended EDL narrative QC (`validate_narrative --include-edl`) | Extended listen-study metrics |
| Pre-clean | **`audio_preclean`** + **GUI offers** at roadmap checkpoints (never auto-enabled) | Same pattern at any new checkpoint |

**Shipped mix path:** Flow 1/2 `master.wav` is built via `mix`/`REMOVED_mix_flow2` (BUILD-065–066), not speech-only concat. Legacy `mux_flow*` remains a single-stage rerun alias only.

---

## Priority implementation waves

### Wave A — Assembly honesty (BUILD-067–069) — **done**

1. **Gap report → EDL** — **shipped:** `vo_pickup` and gap placements in `edl.json`.
2. **NLE → selection** — **shipped:** `nle_edits.json` overrides applied in `full_master_ranking` and `edl`.
3. **Speech preview** — **shipped:** `assembly_preview.wav` (speech + VO, no MMAudio SFX) after ranking for operator listen-before-SFX.

### Wave B — Coherent sound + mix (BUILD-060–066) — **done**

See [sound-design.md](./sound-design.md), [local-audio-stack.md](./local-audio-stack.md), and [build-out/README.md](../build-out/README.md#wave-5--coherent-sound-design-done).

**Shipped:** SDP init + palettes, flow plans, craft/generate, `mix`/`REMOVED_mix_flow2` in pipeline + GUI.

**Design companion:** [source-derived-sonic-mix-profile.md](./source-derived-sonic-mix-profile.md) — `source_acoustic_profile` (BUILD-082) feeds palettes and craft.

### Wave C — QA and mastering (BUILD-070–071) — **done**

- `verify_master.py`: integrated LUFS, true peak, duration rules per [evaluation-metrics.md](./evaluation-metrics.md).
- Measured loudness on assembly bus; GUI surfaces failures.

### Wave C2 — Extended EDL narrative checks — **done**

- `edl_narrative_audit`: local LLM frames the volley, then flagship routing reviews final Flow 1 narrative readiness before EDL build.
- `edl_narrative_qc`: deterministic strict gate on final `edl.json` semantics — coverage survives NLE, chapters remain coherent, ordering constraints hold, transitions align, and gap placements match VO clips.
- CLI: `python tools/validate_narrative.py --run-id <exec_id> --include-edl` runs upstream narrative, EDL timeline, and EDL narrative checks together.

### Wave D — Audio pre-clean (BUILD-019 + BUILD-072) — **done**

- `audio_preclean` stage shipped (local MMAudio, optional).
- **Quality offers** at two checkpoints — see [audio pre-clean](../pipeline/audio_preclean/README.md#when-the-operator-is-offered-pre-clean).
- Pickup-only scope (`vo_pickup`) when operator records gap-fill lines at G1.

---

## Operator quality offers (non-blocking)

These are **optional** prompts in the GUI (and future CLI flags), not gates G0–G2. The operator can accept or dismiss at any time.

| Checkpoint | Offer |
|------------|--------|
| Before ingest | Clean source interview background noise |
| **G1 — after recording pickup questions** | Clean **new VO files** in `vo_pickup/` (room tone on mic, HVAC) |

**G1 follow-up (important):** When the operator records **additional interviewer questions** to fill gaps, the app should explicitly offer: *“Remove background noise from your new pickup recordings?”* This is separate from cleaning the original interview — only `vo_pickup/*.wav` (or a merged pickup bus) need isolation.

Re-running pre-clean invalidates downstream markers from **ingest** (or from **vo_ingest** for pickup-only cleans) — see [idempotent-runs.md](../workflows/idempotent-runs.md).

---

## Recommended operator journey

```mermaid
flowchart LR
  CAP[Capture] --> Q1{Offer pre-clean?}
  Q1 --> ING[Ingest + STT]
  ING --> G0[G0 transcript]
  G0 --> AN[Analysis]
  AN --> G1[G1 VO pickup]
  G1 --> Q2{Offer clean new VO?}
  Q2 --> G2[G2 flow pick]
  G2 --> SEL[Selection + narrative]
  SEL --> PRE[Preview assembly]
  PRE --> G15{G1.5 SFX approve optional}
  G15 --> MIX[Mix + master]
  MIX --> QA[verify + listen]
```

---

## Related docs

- [build-out/remaining-build-commands.md](../build-out/remaining-build-commands.md) — open Agent work queue
- [build-out/repository-map.md](../build-out/repository-map.md) — code ↔ docs layout
- [pipeline.md](../pipeline.md) — stage overview
- [operator-gates.md](../workflows/operator-gates.md) — mandatory stops + quality offers
- [audio_preclean/README.md](../pipeline/audio_preclean/README.md) — pre-clean semantics
- [assembly_and_mux/README.md](../pipeline/assembly_and_mux/README.md) — mix vs legacy mux alias
- [evaluation-metrics.md](./evaluation-metrics.md) — pass/fail for masters
