# Operator gates

Mandatory human checkpoints. Agents **must stop** at these gates — do not auto-continue.

**Quality offers** (optional, non-blocking) are separate from gates — see [Quality improvement offers](#quality-improvement-offers-not-gates) and [audio pre-clean](../pipeline/audio_preclean/README.md). ElevenLabs/ffmpeg pins: [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md).

---

## GUI operator console (checkpoints + API consent)

The web GUI enforces gates visually and blocks **Run next stage** while any stage is `action_required`.

| Mechanism | Operator experience |
|-----------|---------------------|
| **Checkpoint banner** | Amber strip when your input is required |
| **Attention ping** | Browser sound on gates / `action` log lines (mute in header) |
| **API consent** | Modal before first use of OpenAI, AWS Transcribe, or ElevenLabs in the session; per-provider grant; revocable via **Revoke API** |
| **File handoff (custom run)** | After each stage that writes **per-interview descriptive JSON** (themes, brief, segments, flow plans, etc.), the pipeline **pauses**; **Outputs from this step** lists those files; edit in **File editor**, then **Acknowledge & continue** before the next automated stage. Controlled by `journey_ui.require_handoff_between_stages` (default `true`). Ingest/STT/checksum paths are excluded. |

See [gui-surface-map.md](./gui-surface-map.md) and [api-reference.md](./api-reference.md).

---

## G0 — Transcript review (STT corrections)

**After:** `transcript_review_build` (runs immediately after `transcribe`)

**Trigger:** `transcript/review_queue.json` exists and `.stage_done/transcript_review` is missing.

**Prompt operator:**

1. Open the GUI stage **Transcript review**
2. Play each ranked clip (lowest AWS confidence first); edit transcript text; save
3. Click **Complete transcript review** (applies corrections to `transcript/full.json`)

**Skip when:** Operator has completed review (marker file present).

**CLI sign-off:** `python -m interview_mux run-stage --run-id … --stage transcript_review`

See [transcript-review.md](../pipeline/transcription/transcript-review.md).

**Quality offer after G0:** If many clips were low-confidence, offer [background noise removal](../pipeline/audio_preclean/README.md) on the full source and re-run from `audio_preclean` → ingest (operator choice).

---

## Profile gate — Flow 1 extended (BUILD-081)

**When:** Before `topic_coverage_audit` (first Flow 1 extended stage), when `run_meta.json` has `selected_flow: flow1`.

**Trigger:** `understanding/analysis_state.json` → `meta.operator_verified` is not `true`, and `.stage_done/topic_coverage_audit` is missing.

**Prompt operator:**

1. Open **Story** or **Profile (JSON)** sub-tabs in Pipeline (or the profile-lock checkpoint CTAs when `topic_coverage_audit` is locked)
2. Adjust **themes**, **major_questions**, **style** (tone, pacing, interviewer/interviewee style)
3. Click **Mark profile verified** (`meta.operator_verified: true`)
4. Re-run Flow 1 from **Topic coverage** or `python tools/run_flow.py --flow flow1`

**Behavior:** Pipeline **blocks** with `SystemExit` and `ctx.log()` at `level=action` (GUI job status `gate`). Flow 1 stages stay **locked** in the stage list until verified. Flow 2 / Flow 3 are not blocked by this gate (Flow 3 warns only on unverified profile).

**Skip when:** Profile verified, or `topic_coverage_audit` already completed (re-run from a later Flow 1 stage).

LLM stages respect verified profile fields unless transcript evidence contradicts — then check `investigation_queue.json` or log `needs`.

See [analysis-memory.md](../cross-cutting/analysis-memory.md), [podcast-quality-roadmap.md](../cross-cutting/podcast-quality-roadmap.md).

---

## G1 — Human VO pickup

**After:** `tools/run_analysis.py` completes (BUILD-028)

**Trigger:** Any `interviewer_lines[]` entry in `gap_report.json` with `delivery: record` and no matching file in `vo_pickup/`.

**Prompt operator:**

1. Open `understanding/interviewer_script.txt` (GUI **G1 VO pickup**)
2. Record each proposed **additional interviewer question** / setup line
3. Save as `vo_pickup/{line_id}.wav` (or `{targets_segment_id}.wav`)
4. Re-run: `python tools/run_analysis.py --from-stage vo_ingest` (or full re-check)

**Skip when:** No `delivery: record` lines, or all pickup files present.

### Quality offer at G1 (required product behavior)

After pickup recordings are saved, **offer background noise removal on the new VO files only**:

- Copy: e.g. *“Remove background noise from your pickup recordings?”*
- Scope: `vo_pickup` — does **not** require re-cleaning the original interview
- If accepted: clean pickup WAVs, then continue to `vo_ingest` / G2

If the operator dismisses, continue without cleaning. They can accept a full-source pre-clean offer later before mix.

See [audio pre-clean — G1 pickup](../pipeline/audio_preclean/README.md#g1-pickup-cleanup-explicit-product-behavior).

---

## G2 — Flow selection

**After:** G1 cleared

**Prompt operator:** Choose output:

- `flow1` — full master podcast (extended analysis + optimal order + podcast SFX)
- `flow2` — highlight reel (≤5 clips + montage SFX)
- `flow3` — podcast show description (~200 words, third person; text only, no mux)

**Persist:**

```json
{ "selected_flow": "flow1", "selected_at": "ISO8601" }
```

in `run_meta.json` (under `ASSETS/executions/…` or legacy `data/run_NNN/`). Use `"flow3"` for the publishing copy path.

**CLI:**

```bash
python tools/run_flow.py --flow flow1
python tools/run_flow.py --flow flow2
# flow3 — show description (text only)
python tools/run_flow.py --flow flow3 --run-id <exec_id>
```

Flow 3 does not require ElevenLabs or mastering. Profile verification is **recommended** before `podcast_show_description` — see [publishing/README.md](../pipeline/publishing/README.md).

---

## G1.5 — Sound design prompt approval (optional, shipped)

**When:** After `elevenlabs_prompt_craft`, **before** `elevenlabs_sfx_flow1` / `elevenlabs_sfx_flow2` generation spend.

**Trigger:** `g1_5_require_prompt_approval: true` in `config/app.defaults.json` (default `false`).

**Action:** Operator reviews and edits `sound_design/elevenlabs_prompts.json` on the **Craft ElevenLabs prompts** stage panel; **Approve** sets `run_meta.json` → `elevenlabs_prompt_review.approved`. Generation is blocked in GUI and at runtime until approved.

See [gui-surface-map.md](./gui-surface-map.md#elevenlabs-operator-journey-sfx--g15) · [elevenlabs-integration-guide.md § GUI operator journey](../cross-cutting/elevenlabs-integration-guide.md#gui-operator-journey).

---

## Quality improvement offers (not gates)

These **do not** block the pipeline unless the operator accepts and a re-run is required.

| Offer | Typical moment | Scope |
|-------|----------------|-------|
| Pre-clean source | Before ingest / new run (acceptance runs `audio_preclean` before `ingest`) | `full_source` |
| Pre-clean after STT pain | After G0 | `full_source` |
| Pre-clean pickup VO | **After G1 recordings** | `vo_pickup` only |
| Pre-clean before SFX spend | After `assembly_preview` — listen speech + VO before ElevenLabs API calls | `full_source` (checkpoint `before_sfx_spend`) |
| Pre-clean before mix | Before `mux_flow*` | `full_source` or `normalized_rebuild` |
| Assembly preview listen | After ranking, before SFX | N/A (listen only) |
| Re-verify master | After `master.wav` | QA + optional re-mux |

Log accept/dismiss in `run_meta.json` → `audio_preclean.offered_at`, `audio_preclean.decisions`, and `gui_log.jsonl` (`stage: audio_preclean`).

**GUI (BUILD-072):** When the operator selects a stage tied to a checkpoint, the workspace shows a non-blocking **Quality offer** card (Accept / Dismiss). Showing the card calls `POST …/preclean-offer` with `action: offer`; buttons send `accept` or `dismiss` with the checkpoint’s default scope (`vo_pickup` at G1). See [gui-surface-map.md](./gui-surface-map.md#quality-offers-pre-clean).

On **accept**, the server clears downstream stage markers (`audio_preclean` → ingest/transcribe for `full_source` / `normalized_rebuild`; `vo_ingest` + flow assembly for `vo_pickup`). Re-run `audio_preclean` then the invalidated stages. Pre-clean **never** runs until accept — the `audio_preclean` stage logs a skip when `enabled` is false.

Default for all offers: **off** — operator opts in.

---

## What we do not ask

- Flow choice before analysis completes
- VO recording for `delivery: synthesize` (deferred in v1)
- Mandatory pre-clean at any step
- Re-confirming gates on idempotent re-runs when artifacts already satisfy checks

## Related

- [gui-surface-map.md](./gui-surface-map.md) — panels ↔ API ↔ `gui_log.jsonl` ↔ artifacts
- [operator-stage-checklists.md](./operator-stage-checklists.md) — per-stage verification tables
- [troubleshooting.md](./troubleshooting.md) — symptom → artifact → re-run playbook
- [feedback-loops-and-reruns.md](./feedback-loops-and-reruns.md) — `--from-stage` recipes
