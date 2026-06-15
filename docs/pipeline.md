# Pipeline — three output flows

**Toolchain:** Pinned Python packages, `ffmpeg`/`aws` CLI, and HTTP API paths — [cross-cutting/anchored-toolchain.md](./cross-cutting/anchored-toolchain.md). Implementers use **Context7** at those exact versions.

One source interview session produces **three possible deliverables** (operator chooses after shared analysis). Early stages are shared; selection, publishing, and assembly diverge after **gate G2**.

**Quality target:** A polished mastered podcast — narrative order, gap-filling VO, cohesive sound design, measured loudness — plus optional **distribution copy** for Flow 3. Flow 1/2 mix via `mix_flow1` / `mix_flow2` (speech + VO + SDP overlays in `master.wav`). Flow 3 ships show-description copy via `publishing_flow3.py` (no audio mux). Stage ids and status: [stage-registry.md](./build-out/stage-registry.md). Remaining quality gaps: [podcast-quality-roadmap.md](./cross-cutting/podcast-quality-roadmap.md).

```mermaid
flowchart TB
    subgraph shared [Shared analysis]
        A0[Capture] --> A1{Offer pre-clean?}
        A1 -->|optional| A1b[Audio isolation]
        A1 -->|skip| A[Ingest]
        A1b --> A
        A --> B[Transcribe + diarize]
        B --> B2[Transcript review G0]
        B2 --> B2q{Offer pre-clean?}
        B2q --> C[Content understanding]
        C --> D[Segmentation]
        D --> E[Interviewer gap analysis]
    end
    E --> G1{G1 VO pickup?}
    G1 --> G1q{Offer clean new VO?}
    G1q --> G2{G2 Pick flow}
    G2 -->|Flow 1| F1[Extended analysis]
    F1 --> F1b[Order + transitions + preview]
    F1b --> F1c[SFX plan + mix]
    G2 -->|Flow 2| F2[Highlight pick]
    F2 --> F2b[Montage SFX + mix]
    G2 -->|Flow 3| F3[Show description]
    F1c --> K[Master + export]
    F2b --> K
    F3 --> T[Text export]
```

---

## Shared foundation

All work starts from a single long-form interview recording in `./ASSETS/`. Operators select the file in the GUI (**Input audio**) or pass `input_audio_path` when creating a run via API; each run persists under `ASSETS/executions/exec_NNN_<hash12>_TIMESTAMP` (same WAV → same hash → per-stage reuse offers) — [cross-cutting/assets-and-executions.md](./cross-cutting/assets-and-executions.md) · [workflows/stage-execution-reuse.md](./workflows/stage-execution-reuse.md).

| Stage | Goal | Key artifacts |
|-------|------|----------------|
| **Audio pre-clean** *(optional)* | Remove background noise before STT/mux | `preclean/isolated.wav`, `preclean/lineage.json` |
| **Ingest** | Normalize format, checksum, session id | `ASSETS/executions/exec_*` workspace, normalized WAV |
| **Transcribe + diarize** | Word-level text with speaker labels | Transcript JSON, speaker map |
| **Transcript review (G0)** | Operator fixes STT using confidence-ranked clips + synced word dock (fuzzy similar-word replace) | `transcript/full.json`, `transcript/corrections.json` |
| **Content understanding** | Themes, narrative arc, who said what (OpenAI **flagship**, gap-fill, validated write) | `analysis_state.json`, content brief, speaker roles — [artifact-generation-and-validation.md](./cross-cutting/artifact-generation-and-validation.md) |
| **Segmentation** | Time-bounded units | Segment manifest |
| **Interviewer gap analysis** | Missing framing, VO script | Gap report |

**Optional pre-clean (two moments):** Background noise removal is **never required** but is **offered** at exactly two checkpoints — before ingest on the raw capture, and **after the operator records additional pickup questions at G1**. Full-source clean improves STT and assembly; pickup-only clean targets new `vo_pickup/` files without re-processing the interview. Default is off. See [audio pre-clean](./pipeline/audio_preclean/README.md).

Run via: `python tools/run_analysis.py`

Analysis uses a **memory-backed orchestrator**: each LLM stage can retry, merge themes/questions into `understanding/analysis_state.json`, and queue investigations. Operators edit the profile in the GUI or JSON files — see [analysis-memory.md](./cross-cutting/analysis-memory.md).

**Gate G1** — human VO for `delivery: record` → [operator-gates.md](./workflows/operator-gates.md)

**Gate G2** — choose `flow1`, `flow2`, or `flow3` before `run_flow.py`

---

## Flow 1 — Full master podcast

**Intent:** Complete episode covering **all usable interview material**, ordered for the best podcast listen, with subtle MMAudio SFX.

### Stage sequence (after G2)

1. **Topic coverage audit** — map every brief topic/claim to segments
2. **Narrative arc plan** — setup → payoff, chapters, ordering constraints
3. **Full master ranking** — optimal segment order (not chronological default)
4. **Transitions** — interviewer bridges
5. **Sound design plan (Flow 1)** — SDP `assets` + `flow_plans.flow1.cues` — [sound-design.md](./cross-cutting/sound-design.md)
6. **EDL narrative audit** — local-volley + flagship review of final timeline readiness (`edl_narrative_audit`)
7. **EDL** — speech + VO + gap placements with extended narrative QC (`edl_flow1`)
8. **Assembly preview** — speech + VO listen before MMAudio SFX generation (`assembly_preview.wav`)
9. **MMAudio SFX prompt craft + SFX** — one WAV per `asset_id` under `sound_design/assets/`
10. **Mix** — `mix_flow1` → `assembly.wav` (speech + VO + beds + stingers)
11. **Master** — `master_flow1` → −16 LUFS — [evaluation-metrics](./cross-cutting/evaluation-metrics.md)

### Success criteria

- All non-aside topics represented or explicitly excluded
- No narrative holes; every included segment `ready` or has VO in EDL
- SFX does not obscure speech; shared assets per [sound-design](./cross-cutting/sound-design.md)

---

## Flow 2 — Highlight reel

**Intent:** ≤5 clips, montage SFX, 60s–3min.

### Stage sequence (after G2)

1. **Highlight selection**
2. **Sound design plan (Flow 2)** — SDP `assets` + `flow_plans.flow2.cues`
3. **MMAudio SFX prompt craft + SFX** — montage assets
4. **Mix** — `mix_flow2` → `assembly.wav` (cold open + shared between-clip transition)
5. **Master** — `master_flow2` → −14 LUFS

---

## Flow 3 — Podcast show description

**Intent:** A **~200-word, third-person** episode blurb that allures and entices listeners — for podcast directories, web pages, and social previews. **No audio output.**

### Stage sequence (after G2)

1. **Podcast show description** — flagship LLM with rich user/assistant context volley (content brief, profile, manifest slice, optional gap summaries)
2. **Export** — `show_description.md` plain text alongside JSON

### Success criteria

- 150–250 words; third person throughout
- Hook, stakes, themes, and audience pitch grounded in `content_brief` / segments
- No invented facts, long transcript quotes, or pipeline jargon

See [pipeline/publishing/README.md](./pipeline/publishing/README.md) and [podcast-show-description.system.txt](./prompts/publishing/podcast-show-description.system.txt).

---

## Flow comparison

| Dimension | Flow 1 | Flow 2 | Flow 3 |
|-----------|--------|--------|--------|
| Output | Mastered WAV (full episode) | Mastered WAV (reel) | Show description (text) |
| Coverage | All usable material | ≤5 clips | Whole-interview narrative |
| Analysis | Shared + extended audit/arc | Shared only | Shared only |
| Ordering | Optimal podcast narrative | Hook → kicker | N/A |
| SFX / mux | Yes | Yes | No |
| Length | Long episode | ≤ ~3 min | ~200 words |
| Model tier (key stage) | Flagship (ranking) | Flagship (selection) | **Flagship** (`podcast_show_description`) |

---

## File structure (per run)

See [cross-cutting/artifact-layout.md](./cross-cutting/artifact-layout.md).

---

## Related docs

- [build-out/implementation-guide.md](./build-out/implementation-guide.md) — full-repository build plan (start here for code)
- [build-out/full-application-flow.md](./build-out/full-application-flow.md) — end-to-end operator journey
- [build-out/stage-registry.md](./build-out/stage-registry.md) — every stage id and status
- [podcast-quality-roadmap.md](./cross-cutting/podcast-quality-roadmap.md) — v1 vs target, priority waves
- [logic-tree.md](./logic-tree.md)
- [prompts/README.md](./prompts/README.md)
- [build-out/README.md](./build-out/README.md) — tickets
- [build-out/ticket-specs.md](./build-out/ticket-specs.md) — acceptance per BUILD id
- [build-out/repository-map.md](./build-out/repository-map.md) — repo ↔ code
- [build-out/steps-forward.md](./build-out/steps-forward.md) — prioritized backlog
- [cross-cutting/sound-design.md](./cross-cutting/sound-design.md) — coherent SFX (BUILD-060+)
- [workflows/gui-surface-map.md](./workflows/gui-surface-map.md) — panels ↔ API ↔ logs
- [workflows/long-interview-chunking.md](./workflows/long-interview-chunking.md) — context caps
- [workflows/operator-gates.md](./workflows/operator-gates.md) — gates + quality offers
- [workflows/operator-flow-audit.md](./workflows/operator-flow-audit.md) — GUI tabs, modals, checkpoints
- [workflows/gui-surface-map.md](./workflows/gui-surface-map.md) — panels ↔ API
- [workflows/operator-stage-checklists.md](./workflows/operator-stage-checklists.md) — per-stage verification
- [workflows/troubleshooting.md](./workflows/troubleshooting.md) — symptom playbook
- [pipeline/transcription/stt-and-diarization.md](./pipeline/transcription/stt-and-diarization.md)
- [pipeline/transcription/source-separation-and-enhancement.md](./pipeline/transcription/source-separation-and-enhancement.md)
- [pipeline/publishing/README.md](./pipeline/publishing/README.md) — Flow 3 copy stage
