# Operator journey

**Start here** for the happy path from interview WAV to podcast master, highlight reel, or show description. Engineers: [AGENTS.md](../../AGENTS.md). Gates: [operator-gates.md](./operator-gates.md). Problems: [troubleshooting.md](./troubleshooting.md).

The GUI reads the same **journey snapshot** as this doc (`GET /api/runs/{id}` → `journey`). Primary CTA label = `journey.next_action`.

---

## Before you start

1. Place audio under `ASSETS/input/` (or anywhere under `ASSETS/` except `executions/`).
2. `./scripts/bootstrap_venv.sh` and `config/secrets/secrets.env` — see [SETUP.md](../../SETUP.md).
3. `./scripts/run.sh` → **Start** tab.

Details: [assets-and-executions.md](../cross-cutting/assets-and-executions.md).

---

## Phase: Prepare

**Goal:** Trust the transcript before AI assigns speaker roles.

1. Optional: accept **audio pre-clean** once ([audio_preclean](../pipeline/audio_preclean/README.md)).
2. Run **Prepare transcript for review** (ingest → transcribe → STT review queue).
3. **G0:** Open transcript review; fix lowest-confidence clips first; **Complete transcript review**.

Go deeper: [transcript-review.md](../pipeline/transcription/transcript-review.md).

---

## Phase: Understand

**Goal:** Shape what the interview is about.

1. Run **Run understanding analysis** (speaker roles through optimal questions).
2. Open **Story** tab — edit themes, questions, tone; resolve open investigations.
3. For **full master** intent: **Lock story for podcast edit** (profile verified).

Go deeper: [analysis-memory.md](../cross-cutting/analysis-memory.md).

---

## Phase: Complete

**Goal:** Fill missing voice and confirm deliverable.

1. **G1:** Record pickup lines to `vo_pickup/` when gap report requires `delivery: record`.
2. Optional: clean **pickup VO only** at G1.
3. **G2:** **Confirm output** — pick flow1 / flow2 / flow3, or click **Use planned choice** if you set intent on the Start tab.

`flow_intent` (Start) is planning only; `selected_flow` (G2) commits execution.

Go deeper: [interviewer-gap README](../pipeline/interviewer-gap/README.md).

---

## Phase: Create

| Intent | Action |
|--------|--------|
| flow1 | **Build episode order → preview** — runs through `assembly_preview.wav` (speech + VO, no SFX spend) |
| flow2 | **Select highlight clips** |
| flow3 | **Generate show description** |

**Listen** to `assembly_preview.wav` before spending on ElevenLabs. Click **I've listened — continue to sound** on the deliverable card.

Express Flow 1: Create CTA + Polish CTA (sound) + Ship CTA (master).

---

## Phase: Polish

1. Optional **G1.5:** Approve ElevenLabs prompts when enabled.
2. **Add sound and export** — craft → SFX → mix.

Go deeper: [operator-sound-and-mix.md](./operator-sound-and-mix.md) · [elevenlabs-integration-guide.md](../cross-cutting/elevenlabs-integration-guide.md).

---

## Phase: Ship

- **flow1/2:** `master.wav` — verify LUFS in Logs (`verify_master`).
- **flow3:** Copy `flow_3_description/show_description.md`.

Go deeper: [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md).

---

## Appendix: `next_action` strings (kernel)

Must match `journey_orchestrator.py` constants (tested in `tests/test_journey_orchestrator.py`).

| Constant | Text |
|----------|------|
| NEXT_ACTION_PREPARE_G0 | Review STT clips (low confidence first) |
| NEXT_ACTION_PREPARE_RUN | Prepare transcript for review |
| NEXT_ACTION_UNDERSTAND_RUN | Run understanding analysis |
| NEXT_ACTION_UNDERSTAND_PROFILE | Lock story in Story Board |
| NEXT_ACTION_UNDERSTAND_INVESTIGATIONS | Resolve open questions in Story Board |
| NEXT_ACTION_COMPLETE_G1 | Record pickup lines |
| NEXT_ACTION_COMPLETE_G2 | Confirm output type |
| NEXT_ACTION_CREATE_FLOW1 | Build episode order → preview |
| NEXT_ACTION_CREATE_FLOW2 | Select highlight clips |
| NEXT_ACTION_CREATE_FLOW3 | Generate show description |
| NEXT_ACTION_POLISH_PREVIEW | Listen to preview, then approve sound |
| NEXT_ACTION_POLISH_SFX | Add sound and mix |
| NEXT_ACTION_SHIP_MASTER | Export master |
| NEXT_ACTION_SHIP_DESC | Export show description |
| NEXT_ACTION_DONE | Deliverable ready — listen or export |

When not blocked, `journey.next_action` matches `execute_hint.label` (single primary CTA string). GUI **command bar** (all tabs) shows status + primary button.

## Journey log kinds

`gate` · `quality` · `preview` · `sfx` · `qc` · `milestone` · `execute` — filter in **Logs** tab (**Journey view**).
