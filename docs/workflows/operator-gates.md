# Operator gates

Mandatory human checkpoints. Agents **must stop** at these gates — do not auto-continue.

**Quality offers** (optional, non-blocking) are separate from gates — see [Quality improvement offers](#quality-improvement-offers-not-gates) and [audio pre-clean](../pipeline/audio_preclean/README.md). ffmpeg / local audio stack pins: [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md).

---

## GUI operator console (checkpoints + API consent)

The web GUI enforces gates visually and blocks **Run next stage** while any stage is `action_required`.

| Mechanism | Operator experience |
|-----------|---------------------|
| **StageStepWorkbench** | Numbered steps in the middle panel: instruction, review checklist, one primary CTA per active step |
| **Attention ping** | Browser sound on gates / `action` log lines (mute in header) |
| **API consent** | **Shipped default:** session execute sends `api_consents: { openai, openai, aws }` (see `frontend/src/utils/index.ts`). Optional consent modal CSS exists but is not wired — operators must have keys in `config/secrets/secrets.env`. Future: per-provider modal per original spec. |
| **File handoff (custom run)** | After each stage that writes **complete** per-interview descriptive JSON (themes, brief, segments, flow plans, etc.), the pipeline **pauses**; review in modal, then **Acknowledge & continue** before the next automated stage. Partial/scaffold files do not trigger handoff. Controlled by `journey_ui.require_handoff_between_stages` (default `true`). Ingest/STT/checksum paths are excluded. |
| **Stage execution reuse** | Before each automated stage (when candidates exist), choose **Reuse outputs** or **Run fresh instead** in the modal. Controlled by `journey_ui.enable_stage_reuse_offers` (default `true`). Not a gate — does not replace G0–G2. |
| **Write approval** | After each automated stage (when enabled), **Review outputs before saving** in modal; preview, edit, **Save & continue** or **Discard & re-run**. Controlled by `journey_ui.require_write_approval_per_stage` (default `true`). Applies to reused copies too. |
| **Steps sidebar substeps** | Navigation checklist only — click opens modal section. `journey.active_substep_id` and `journey.active_operator_action` mirror focus. `actionBusy` shows running substeps (write approval, profile verify, handoff). |
| **Operator feedback** | No silent blocked clicks — `guardBusy` on primaries; job terminal toasts; checkpoint saves use `advanceFromCheckpoint`. See [gui-flow-hardening.md](./gui-flow-hardening.md). |

See [ux-operator-model.md](./ux-operator-model.md), [gui-flow-hardening.md](./gui-flow-hardening.md), [gui-surface-map.md](./gui-surface-map.md), [stage-execution-reuse.md](./stage-execution-reuse.md), and [api-reference.md](./api-reference.md).

---

## G0 — Transcript review (STT corrections)

**After:** `transcript_review_build` (runs immediately after `transcribe`)

**Trigger:** `transcript/review_queue.json` exists and `.stage_done/transcript_review` is missing.

**Prompt operator:**

1. Open the GUI stage **Transcript review** (checkpoint modal opens when G0 is pending)
2. For each ranked clip (lowest AWS confidence first): play audio; fix words in the **synced transcript dock** (double-click a word) or bulk-edit the chunk textarea and **Save chunk**
3. When the same mishearing appears elsewhere, use **Fix similar words** while editing — adjust match strictness (80–100%), then **Replace N words** to batch-correct duplicates
4. Click **Complete transcript review** (merges chunk corrections into `transcript/full.json`; dock edits are already in `full.json`)

**Skip when:** Operator has completed review (marker file present).

**CLI sign-off:** `python -m interview_mux run-stage --run-id … --stage transcript_review`

See [transcript-review.md](../pipeline/transcription/transcript-review.md).

---

## G0.5 — Disfluency review (filler clips)

**After:** `disfluency_extract` (runs after G0 transcript review when `disfluency_extract.enabled`)

**Trigger:** `transcript/disfluencies.json` has events and `.stage_done/disfluency_review` is missing.

**Prompt operator:**

1. Open **Disfluency review** in the GUI (checkpoint when G0.5 is pending)
2. Listen to each filler clip; **Confirm** or **Reject**
3. For confirmed events, toggle **Include in assembly restore** if desired
4. **Complete review** when no events remain pending

**Skip when:** `disfluency_extract.enabled` is false (auto-complete), or zero events after extract, or review marker present.

**CLI sign-off:** `python -m interview_mux run-stage --run-id … --stage disfluency_review`

See [disfluency-extract.md](../pipeline/transcription/disfluency-extract.md).

---

## LLM stage gate — flow hardening

**When:** Any **critical** LLM stage fails completion truth (`complete_llm_stage_or_halt`) or cross-artifact validation at a segmentation boundary.

**Trigger:** Envelope not `complete`, producer artifact incomplete, preflight failure, or cross-artifact mismatch. GUI maps `SystemExit` to job status **`gate`**.

**Prompt operator:**

1. Read the gate message for `stage_key` and artifact path
2. Open `understanding/stage_runs/<stage>/attempt_*.json` and the producer JSON cited
3. Fix upstream artifacts (G0 transcript, speakers, manifest, gap files) or use **Fill gaps**
4. Re-run from that stage: `python tools/run_analysis.py --run-id … --from-stage <stage>` (or Flow equivalent)

**Skip / soften:** Set `analysis.flow_hardening.enabled: false` for legacy dev scripts; or `strict_critical_stages: false` to log without halting critical stages.

See [LLM-ANALYSIS-ARCHITECTURE.md §18](../../LLM-ANALYSIS-ARCHITECTURE.md#18-flow-hardening), [troubleshooting.md](./troubleshooting.md).

---

## Analysis artifacts gate — flow entry

**When:** Starting Flow 1 / 2 / 3 with hardening enabled.

**Trigger:** Any analysis-ready artifact not `complete` (`require_analysis_artifacts_complete`).

**Action:** Finish analysis through `optimal_questions` with complete on-disk artifacts before flows.

---

## Profile gate — Flow 1 extended (BUILD-081)

**When:** Before `topic_coverage_audit` (first Flow 1 extended stage), when `run_meta.json` has `selected_flow: flow1`.

**Trigger:** Understanding analysis has completed (`optimal_questions` done and `analysis_state` populated), `meta.operator_verified` is not `true`, and `.stage_done/topic_coverage_audit` is missing. The profile gate stays **locked** until AI analysis populates the profile — not at run create.

**Prompt operator:**

1. Open **Story** or **Profile (JSON)** sub-tabs in Pipeline (or the profile checkpoint when `analysis_profile` is `action_required`)
2. **Review** AI-generated **themes**, **major_questions**, **style** (tone, pacing, interviewer/interviewee style); edit only if needed
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

If the operator dismisses, continue without cleaning.

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

Flow 3 does not require MMAudio SFX or mastering. Profile verification is **recommended** before `podcast_show_description` — see [publishing/README.md](../pipeline/publishing/README.md).

---

## G1.5 — Sound design prompt approval (optional, shipped)

**When:** After `sfx_prompt_craft`, **before** `mmaudio_sfx_flow1` / `mmaudio_sfx_flow2` generation spend.

**Trigger:** `g1_5_require_prompt_approval: true` in `config/app.defaults.json` (shipped default `true`).

**Action:** Operator reviews and edits `sound_design/sfx_prompts.json` on the **Craft MMAudio prompts** stage panel; **Approve** sets `run_meta.json` → `sfx_prompt_review.approved`. Generation is blocked in GUI and at runtime until approved.

See [gui-surface-map.md](./gui-surface-map.md#mmaudio-operator-journey-sfx--g15) · [local-audio-stack.md § GUI operator journey](../cross-cutting/local-audio-stack.md#gui-operator-journey).

---

## Quality improvement offers (not gates)

These **do not** block the pipeline unless the operator accepts and a re-run is required.

| Offer | Typical moment | Scope |
|-------|----------------|-------|
| Pre-clean source | Before ingest / new run (acceptance runs `audio_preclean` before `ingest`) | `full_source` |
| Pre-clean pickup VO | **After G1 recordings** | `vo_pickup` only |
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
