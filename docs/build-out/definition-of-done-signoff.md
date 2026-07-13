# Definition of done — manual sign-off

**Purpose:** Release-candidate checklist for operators and maintainers. Automated `pytest` is optional; complete this doc (and [smoke-test.md](../workflows/smoke-test.md)) before calling the repository “done.”

**Post gap-closure (2026):** Orchestration loops (envelope `needs`, investigation drain on flow LLM stages, specialist pre-pass for `missing_framing`, mix completeness gate, adaptive crossfade / word-boundary cuts, local pre-clean fallback) are shipped in code — use sections 1–5 below to validate on a real `exec_*` fixture.

**Code anchors:** `src/interview_mux/pipeline.py` · `src/interview_mux/web/stages.py` · [stage-registry.md](./stage-registry.md)

**Related:** [implementation-guide.md](./implementation-guide.md#definition-of-done-entire-app) · [steps-forward.md](./steps-forward.md#definition-of-done-repository-wide) · [repository-map.md](./repository-map.md)

---

## Automated verification (code / CI)

These checks do not replace sections 1–5 below (real `exec_*` + listen tests), but should pass before manual sign-off:

| Check | Command |
|-------|---------|
| Prerequisites + pip-audit | `./tools/check_prerequisites.sh` |
| GUI bundle present | `CHECK_GUI_BUNDLE=1 ./tools/check_prerequisites.sh` |
| Stage parity | `pytest tests/test_stage_parity.py -q` |
| GUI gitignore + bundle | `pytest tests/test_gui_bundle.py -q` |
| Full unit suite | `pytest tests/ -q` |

**2026 audit fixes:** `/ASSETS/` gitignore anchor (no longer ignores `web/static/assets/`); `interview_mux.gui_bundle.needs_gui_build()` in `run.sh`; static bundle committed under `src/interview_mux/web/static/assets/`.

**June 2026 finish (step 07, automated):** `pytest tests/ -q` — 727 passed; `python tools/audit_stage_plans_doc.py` — OK; `./tools/check_prerequisites.sh` — OK; stage parity script — OK. Manual sections 1–6 below still require operator on real `exec_*`.

---

## How to use

1. Fresh machine or clean venv: follow [smoke-test.md](../workflows/smoke-test.md) prerequisites.
2. Work through each section below; check `[x]` only when verified on a real `exec_*` run.
3. Record `run_id`, date, and operator initials in **Sign-off record** at the bottom.
4. After sign-off, update [implementation-guide.md](./implementation-guide.md) and [steps-forward.md](./steps-forward.md) “fresh clone / smoke” checkboxes if all three flows passed.

---

## 1. ASSETS end-to-end (picker, `exec_*`, resume)

| Step | Action | Pass criteria |
|------|--------|---------------|
| 1.1 | Place a `.wav` under `ASSETS/input/` | File appears on home **Input audio** list (`GET /api/assets`) |
| 1.2 | `./scripts/run.sh` → pick file → **New execution** | New folder `ASSETS/executions/exec_NNN_<timestamp>/` with `run_meta.json` (`input_audio_path` set) |
| 1.3 | Run at least through `ingest` | `ingest/normalized.wav`, `gui_log.jsonl` lines via `RunContext.log()` only |
| 1.4 | Stop server (`Ctrl+C`), `./scripts/run.sh` again | Home shows **Previous executions** |
| 1.5 | Restart `./scripts/run.sh` or refresh browser | Auto-restore same `exec_*`, tab, stage; markers, artifacts, log tail intact; `active_execution.json` matches |

**No `INPUT_AUDIO_PATH` required** for GUI-created runs. Headless fallback: `secrets.env` / `--run-id` per [assets-and-executions.md](../cross-cutting/assets-and-executions.md).

- [ ] 1.1–1.5 passed  
- [ ] `run_id` used: ____________________

---

## 1b. Session & UI truth (2026 session overhaul)

| Step | Action | Pass criteria |
|------|--------|---------------|
| 1b.1 | Refresh browser mid-run | `SessionBanner` shows run id, exec #, working dir; same stage/tab restored |
| 1b.2 | `./scripts/run.sh` restart | Fresh Start tab (session cleared); resume prior `exec_*` from **Executions** if needed |
| 1b.3 | Skip `audio_preclean` | Outputs panel shows skip / n/a — never pending `provider.json` |
| 1b.4 | Stage with write approval | Staged badge → **Save to working directory** → files at final paths, stage `done` |
| 1b.5 | Second execution, same WAV | `PreviousSessionReusePanel` + immediate-previous reuse only |
| 1b.6 | Pipeline tab | No **Audio quality (optional)** drawer; no `/audio-quality` network calls |

Automated: `pytest tests/test_session_active_ui_fields.py tests/test_stage_outputs_skip.py tests/test_ui_truth_invariants.py -q`; `python tools/ui_truth_smoke.py --run-id <exec_*>`.

- [ ] 1b.1–1b.6 passed

---

## 2. G2 — all three flows (CLI + GUI)

**Code:** `gates.set_REMOVED_selected_flow` accepts `flow1` \| `flow2` \| `flow3` (`src/interview_mux/gates.py`); CLI `tools/run_delivery.py` and GUI `POST /api/runs/{run_id}/execute` with `mode: flow1|flow2|flow3` (`src/interview_mux/cli.py`, `src/interview_mux/web/server.py`, `web/runner.py`).

Complete shared analysis through G1 (or confirm G1 not required for your fixture) before flow work.

### Flow 1

| Path | Steps | Pass |
|------|-------|------|
| GUI | G2 → choose **Full master podcast** → run flow (or step through stages) | `run_meta.REMOVED_selected_flow` = `flow1`; flow stages visible in workspace |
| CLI | `python tools/run_delivery.py --flow flow1 --run-id <exec_id>` | Reaches `master/master.wav` without unhandled exit |

- [ ] Flow 1 GUI  
- [ ] Flow 1 CLI  

### Flow 2

Use a run with G2 = `flow2` (new execution or change flow in GUI before flow stages).

| Path | Steps | Pass |
|------|-------|------|
| GUI | G2 → **Highlight reel** → run flow | `REMOVED_selected_flow` = `flow2` |
| CLI | `python tools/run_delivery.py --flow flow2 --run-id <exec_id>` | `REMOVED_flow2/master.wav` exists |

- [ ] Flow 2 GUI  
- [ ] Flow 2 CLI  

### Flow 3

| Path | Steps | Pass |
|------|-------|------|
| GUI | G2 → **Show description** → run flow | `show_notes/show_description.md` present; no `master.wav` |
| CLI | `python tools/run_delivery.py --flow flow3 --run-id <exec_id>` | JSON + markdown export; ~150–250 words |

- [ ] Flow 3 GUI  
- [ ] Flow 3 CLI  

---

## 3. Flow 1 / 2 master — VO + SFX mix (listen)

**Not** speech-only concat. Canonical stages: `mix` / `REMOVED_mix_flow2` → `master_finalize` / `REMOVED_master_flow2` (`pipeline.py` `DELIVERY_ORDER` / `REMOVED_FLOW2_ORDER`).

| Check | How |
|-------|-----|
| Artifacts | `master/assembly.wav` (or flow 2 equivalent) before master; `sound_design/assets/*.wav` or flow `sfx/` populated after `mmaudio_sfx_*` |
| Listen | `master.wav`: VO bridges (if G1 lines existed), beds/stingers audible — not dry speech-only |
| Metrics | `python tools/verify_master.py <path-to-master.wav>` exits 0 (Flow 1: −16 LUFS ±1; Flow 2: −14 LUFS ±1) |

Optional: `assembly_preview.wav` (speech + VO, no MMAudio SFX) listened **before** SFX spend.

- [ ] Flow 1 listen + `verify_master`  
- [ ] Flow 2 listen + `verify_master`  

---

## 4. Pre-clean — offered at checkpoints, never auto

**Code:** `audio_preclean` runs only when operator accepts an offer (`run_meta.audio_preclean.enabled`); `POST /api/runs/{run_id}/preclean-offer` (`src/interview_mux/web/server.py`). Checkpoints: [operator-gates.md](../workflows/operator-gates.md#quality-improvement-offers-not-gates), [gui-surface-map.md](../workflows/gui-surface-map.md#quality-offers-pre-clean).

| Checkpoint | Scope (typical) | Verify |
|------------|-----------------|--------|
| Before ingest | `full_source` | Card appears; **Dismiss** → ingest uses original; no `preclean/isolated.wav` unless accepted |
| After transcript review | `full_source` | Offer logged; dismiss does not block analysis |
| G1 VO pickup | `vo_pickup` | Accept → re-run `audio_preclean` + `vo_ingest`; dismiss → continue with raw pickups |
| Before mix (flow) | per roadmap | Offer only; never silent auto-run |

- [ ] At least one checkpoint: offer shown, dismiss works  
- [ ] At least one accept (optional): `preclean/lineage.json` + expected scope in `run_meta.json`  
- [ ] Confirmed: pipeline never enables pre-clean without explicit accept  

---

## 5. Stage registry ↔ `pipeline.py` ↔ `web/stages.py`

**Automated parity (run from repo root):**

```bash
source .venv/bin/activate
python -c "
import sys; sys.path.insert(0, 'src')
from interview_mux.pipeline import ANALYSIS_ORDER, DELIVERY_ORDER, REMOVED_FLOW2_ORDER, REMOVED_FLOW3_ORDER
from interview_mux.web.stages import EXECUTABLE_ORDER
for name, pipe in [('analysis', ANALYSIS_ORDER), ('podcast', DELIVERY_ORDER), ('flow2', REMOVED_FLOW2_ORDER), ('flow3', REMOVED_FLOW3_ORDER)]:
    web = EXECUTABLE_ORDER[name]
    assert list(pipe) == list(web), (name, set(pipe)^set(web))
print('parity OK')
"
```

| Source | Role |
|--------|------|
| `pipeline.py` | `ANALYSIS_ORDER`, `DELIVERY_ORDER`, `REMOVED_FLOW2_ORDER`, `REMOVED_FLOW3_ORDER` — execution order |
| `web/stages.py` | `EXECUTABLE_ORDER` — GUI stage list metadata |
| [stage-registry.md](./stage-registry.md) | Human index; gates + legacy aliases documented |

Gates in GUI but not in `ANALYSIS_ORDER` (expected): `transcript_review`, `analysis_profile`, `g1_vo_pickup`, `REMOVED_g2_flow_select`. Legacy rerun ids: `mux_flow1`, `mux_flow2`, `podcast_sfx_brief`, `sfx_brief`.

- [x] Parity script exits OK  
- [ ] Spot-check: new shipped stage has a row in [stage-registry.md](./stage-registry.md)  

---

## 6. Smoke-test.md — all three flows

Follow [smoke-test.md](../workflows/smoke-test.md) end-to-end on one fixture interview (long enough for G1 optional, short enough for CI time).

| Section | Key artifacts / commands |
|---------|---------------------------|
| Prerequisites | `bootstrap_venv.sh`, `check_prerequisites.sh`, secrets + AWS |
| GUI path | Picker + resume (§ ASSETS above) |
| Analysis CLI | `run_analysis.py`, `analysis_complete.json` |
| Flow 1 | `run_flow.py --flow flow1`, `verify_master.py` on `master/master.wav` |
| Flow 2 | `run_flow.py --flow flow2`, `verify_master` on `REMOVED_flow2/master.wav` |
| Flow 3 | `run_flow.py --flow flow3`, `show_description.md`, no master WAV |

**Note:** Automated `pytest tests/` is optional for release sign-off; use this doc + smoke-test for release candidate.

- [ ] smoke-test.md prerequisites  
- [ ] smoke-test.md analysis section  
- [ ] smoke-test.md Flow 1 section  
- [ ] smoke-test.md Flow 2 section  
- [ ] smoke-test.md Flow 3 section  

---

## 7. Quality-first listen checklist (per stage category)

From [llm-guidance-program.md](../cross-cutting/llm-guidance-program.md) and [stage-quality-scorecard.md](../cross-cutting/stage-quality-scorecard.md). For each tier, verify on a real `exec_*` run that artifacts are **complete**, arbiter **accept** (or justified operator override), and listen/export criteria pass before calling the category done.

### P0 — Foundation (understanding / segmentation)

| Stage | Listen / read check |
|-------|---------------------|
| `speaker_roles` | Interviewer vs interviewee matches who asks questions in transcript sample |
| `content_context` | Thesis is interviewee-faithful; topics map to real discussion (no generic filler) |
| `boundary_detection` | Segment splits align with pauses and topic shifts — spot-check 5 boundaries in GUI |
| `segment_classification` | Types (`interviewee_answer`, `interviewer_question`, etc.) match transcript turns |
| `content_brief_reanchor` | Major `topics[].segment_ids` non-empty and plausible |

- [ ] P0 read/listen spot-check passed on fixture run

### P1 — Narrative comprehension (Flow 1 extended)

| Stage | Listen / read check |
|-------|---------------------|
| `missing_framing` | Gap types match “would a listener understand this clip?” — no false `ok` on orphan answers |
| `optimal_questions` | Proposed VO lines ≤ word caps; sound natural when read aloud |
| `topic_coverage_audit` | Brief topics either covered or explicitly flagged missing |
| `narrative_arc_plan` | Chapter flow matches intended story; ordering constraints achievable |
| `full_master_ranking` | `ordered_segment_ids` tell a coherent arc when skim-reading manifest text in order |
| `edl_narrative_audit` | No critical findings blocking EDL; transitions and gap placements cited |

- [ ] P1 narrative read check passed
- [ ] `validate_narrative.py` (and `--include-edl` if strict) exits 0

### P2 — Sound design + mix (SDP path)

| Stage | Listen / read check |
|-------|---------------------|
| `sound_design_palettes` | `coherence.sonic_identity` matches interview tone (not generic trailer) |
| `sound_design_plan` / `flow2` | Cue count within caps; placements anchor to real segment/rank boundaries |
| `assembly_preview` | Speech + VO intelligible; no SFX yet — **listen before MMAudio SFX generation** |
| `sfx_prompt_craft` | Prompts instrumental; no voice/policy leaks; G1.5 approved if enabled |
| `mmaudio_sfx_flow*` | Generated beds/stingers match prompt intent on spot-listen (2 assets minimum) |
| `mix_flow*` → `master_*` | Beds duck under speech; VO bridges present; not dry speech-only |

- [ ] `assembly_preview` listened before SFX generation
- [ ] P2 mix listen + `verify_master.py` passed (§3 above)

### P3 — Polish

| Stage | Listen / read check |
|-------|---------------------|
| `transitions` | Bridge lines match interviewer style; no duplicate content |
| `REMOVED_highlight_selection` | ≤5 clips; each self-contained or single micro-setup |
| `REMOVED_podcast_show_description` | Third person; ~150–250 words; no invented facts |

- [ ] P3 polish read check passed (Flow 2/3 as applicable)

### P4 — Upstream non-LLM gates

| Gate / stage | Check |
|--------------|-------|
| G0 transcript review | Low-confidence words corrected; `full.json` merged |
| `source_acoustic_profile` | Pause ladder and RMS profile plausible for source audio |
| `disfluency_extract` | Filler catalog sane; restore optional per operator |
| Spend block | Craft/generate did not run with incomplete SDP (no wasted API calls) |

- [ ] P4 upstream gates verified on fixture run

---

## 6. Nine-scenario sonic listen matrix (BUILD-SFX-17)

Use `tests/fixtures/sonic_context/*.json` atlas buckets as listen posture references. On a real `exec_*` run, spot-check one representative interview per bucket (or nearest match) before SFX spend:

| Atlas bucket | Listen posture | Pass if |
|--------------|----------------|---------|
| `one_on_one` | Sparse beds; soft stingers | Speech always forward; no trailer hits |
| `panel` | No beds under overlap/crosstalk | Beds absent on multi-speaker overlap segments |
| `fireside` | Minimal beds; gentle rises | Warm, not hype; no percussion stabs |
| `technical_deep_dive` | No beds; rare stingers | No cinematic drama or cartoon SFX |
| `media_profile` | Sparse; broadcast-neutral | No tabloid/sensational cues |
| `debate` | No beds; very low stinger rate | No conflict-escalating impacts |
| `noisy_room` | No beds; no bright risers | Nothing masks already-difficult speech |
| `dense_jargon` | Minimal; no lyrical beds | No harmonic clutter over terminology |
| `trauma_adjacent` | No beds/stingers on flagged segments | No playful motifs or loud transients |

- [ ] 6. Nine-scenario matrix spot-checked (note bucket + `run_id` in sign-off record)

**Wave 0 harness (2026-06):** Automated fixture coverage via `pytest tests/test_sonic_context.py tests/test_sound_design_scenario.py tests/test_mix_acoustic_profile.py -q` satisfies CI-07 until a full listen pass on nine real `exec_*` runs. Prosody diversity (SC-12): deferred manual hard-listener clips — see [02-WAVE-0 §4](./june182026build/02-WAVE-0-resilience-harness.md#4-prosody--delivery-guardrails).

---

## Sign-off record

**Manual sections 1–6** require a real interview WAV and operator time — complete on your machine before release candidate.

**June 2026 build (steps 01–07):** Code complete; automated CI green (see table below). Operator completes §1–6 when ready.

| Field | Value |
|-------|--------|
| Date | |
| Operator | |
| `exec_*` (flow1/2/3) | |
| Git commit (optional) | |
| Notes | |
| Automated suite (June 2026 finish) | `pytest tests/ -q` — 727 passed; `python tools/audit_stage_plans_doc.py` — OK; `./tools/check_prerequisites.sh` — OK; stage parity — OK |

**Maintainer:** When all sections are checked, mark fresh-clone items in [implementation-guide.md](./implementation-guide.md) and [steps-forward.md](./steps-forward.md), and link this file from [AGENTS.md](../../AGENTS.md) / [INDEX.md](../INDEX.md).
