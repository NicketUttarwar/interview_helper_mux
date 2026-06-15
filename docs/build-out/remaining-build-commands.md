# Remaining build commands — Cursor Agent queue

> **Gap closure (sections #2 / #5):** Shipped — see [gap-closure-agent-commands.md](./gap-closure-agent-commands.md) for the historical 16-command sequence and architecture notes.

**Purpose:** Copy-paste **one command per Agent chat** for work that is **not yet shipped**. All core BUILD tickets (Waves 1–7, including 060–073, 080–082) are **done in code** — this file replaces the appendix in [steps-forward.md](./steps-forward.md) for what is left.

**Supersedes:** Do not re-run BUILD prompts from `steps-forward.md` Appendix Commands 1–15 or backlog steps marked **shipped** / ~~done~~ in [README.md](./README.md).

**How to use**

1. Open **Agent mode** in Cursor.
2. **Commands 1–7 and 9–15 are done** — only **Command 8** (optional SSL moonshot) remains for R&D.
3. Re-run a done command only when docs drift after a code PR.
4. Copy the **Agent prompt** block; `@`-attach listed docs.
5. Use **Done when** checks only (no pytest required for this guide unless a command says otherwise).
6. Update [README.md](./README.md), [repository-map.md](./repository-map.md), and [doc-maintenance.md](./doc-maintenance.md) when a command closes a gap.

**Always-on:** `.cursor/rules/interview-helper-mux.mdc` · [AGENTS.md](../../AGENTS.md)

---

## Doc coverage map (who owns what)

Command 1 covered build-out + selected cross-cutting docs. **Commands 2 and 9** finish the rest of the doc tree. Code commands (3–8) include doc updates for the artifacts they touch.

| Doc / area | Command |
|------------|---------|
| `docs/build-out/*` (README, implementation-guide, stage-registry, steps-forward, repository-map, full-application-flow, g15 guide) | **1** ✓ |
| `docs/cross-cutting/podcast-quality-roadmap.md`, `json-schema-coverage.md` | **1** ✓ |
| `docs/pipeline.md`, `docs/README.md`, `docs/INDEX.md` | **2** ✓ |
| `docs/workflows/operator-stage-checklists.md`, `troubleshooting.md`, `operator-gates.md` (if drift) | **2** ✓, **4** ✓, **5** ✓, **9** ✓ |
| `docs/cross-cutting/sound-design.md`, `anchored-toolchain.md`, `artifact-layout.md`, `source-derived-sonic-mix-profile.md` | **2** ✓, **3** ✓, **8** (deps if SSL promoted) |
| `docs/pipeline/*/README.md` (assembly, scoring, publishing, audio_editing, …) | **2** ✓, **4** ✓, **9** ✓ |
| `docs/prompts/README.md`, `analysis-stage-matrix.md` | **2** ✓, **9** ✓ |
| `docs/workflows/gui-surface-map.md`, `api-reference.md`, `local-audio-stack.md` | **5** ✓, **9** ✓ |
| `docs/cross-cutting/evaluation-metrics.md` | **4** ✓, **9** ✓ |
| `docs/pipeline/value-analysis/*` | **7** ✓, **8** (optional) |
| `docs/build-out/definition-of-done-signoff.md` | **9** ✓ |
| `docs/roadmap/future-proofing.md`, `config-keys.md` | **6** ✓, **8** (optional) |

---

## What is already shipped (do not re-implement)

| Area | Status |
|------|--------|
| ASSETS / `exec_*` runs, GUI resume | Shipped — [repository-map.md](./repository-map.md) |
| Flow 1/2/3 pipelines, G0–G2, profile gate (081) | Shipped |
| Sound design Wave 5 (060–066): SDP, palettes, flow plans, craft, mix | Shipped |
| Assembly Wave 6 (067–069): EDL + VO, NLE overrides, assembly preview | Shipped |
| Mastering QA (070–071), pre-clean stage + GUI offers (019, 072) | Shipped |
| Smart LLM routing (073), source acoustic profile (082) | Shipped |
| G1.5 approve gate + prompt review API/GUI | Shipped — `g15_prompt_review.py`, `frontend/…/SfxPromptReviewPanel.tsx` |
| G1.5 listen-result API + post-listen GUI (`POST …/listen-result`, Pass/Fail panels) | **Shipped** |
| Value-analysis CLIs (`run_value_spike.py`, `extract_value_features.py`) | Shipped — **not** on default `pipeline.py` |
| Value-features read-only GUI on `content_context` | Shipped — when `value_analysis.enabled` |
| Value-features auto-extract after `content_context` | **Shipped** — `value_analysis.auto_extract_after_content_context` (default **on** in `config/app.defaults.json`) |
| **Command 1** — build-out / cross-cutting doc coherence | **Done** — see [Command 1](#command-1--documentation-coherence-sweep-done) |

---

## Command 1 — Documentation coherence sweep (**done**)

Align build-out and cross-cutting docs with shipped code. **No production behavior changes** unless you find a one-line doc bug that requires a comment in code.

Re-run only if build-out or cross-cutting docs drift after a code PR.

**Agent prompt:**

```text
Documentation coherence only — no new features, no pytest.

Read:
@docs/build-out/README.md
@docs/build-out/implementation-guide.md
@docs/build-out/stage-registry.md
@docs/build-out/steps-forward.md (Now table + Definition of done)
@docs/build-out/repository-map.md
@docs/build-out/g15-and-value-analysis-execution.md
@docs/cross-cutting/podcast-quality-roadmap.md
@docs/cross-cutting/json-schema-coverage.md
@docs/build-out/full-application-flow.md
@src/interview_mux/pipeline.py
@src/interview_mux/web/server.py

Update so docs match code today:
- Mark Waves 5–6 tickets done in README; implementation-guide Phases 5–6 → done (not "planned")
- stage-registry G2: flow1 | flow2 | flow3 shipped; remove "partial" if server accepts flow3
- steps-forward: strike #0, #2, #4, #6–#17 appendix duplicates; point "what's next" to remaining-build-commands.md
- podcast-quality-roadmap: v1 table reflects mix_flow*, assembly_preview, pre-clean offers (not "until Wave 5")
- full-application-flow: pickup-scoped pre-clean → shipped (vo_pickup scope in audio_preclean.py)
- json-schema-coverage: edl_flow1.schema.json exists — note "schema yes, validator wiring" per Command 3
- g15 guide: listen-result API, value_features panel, and post-listen GUI shipped

Follow @docs/build-out/doc-maintenance.md. No operator-facing strings outside gui_log policy.
```

**Done when:** No doc in the Command 1 read list still claims flow3, full mix, or G1.5 core are unshipped; [remaining-build-commands.md](./remaining-build-commands.md) is linked from [README.md](./README.md) Start here table.

---

## Command 2 — Documentation hub sweep (**done**)

Historical agent prompt preserved below. Re-run only after doc drift.

Finish doc coherence **outside** Command 1 scope: entrypoint hubs, operator workflows, pipeline stage READMEs, and cross-cutting specs that still say "planned" or "speech-only mux".

**Agent prompt:**

```text
Documentation hub sweep only — no new features, no pytest.

Read (grep each for: speech-only, until Wave 5, until BUILD-065, until BUILD-067, (planned), v1 gap, flow1 | flow2 only):
@docs/pipeline.md
@docs/README.md
@docs/INDEX.md
@docs/workflows/operator-stage-checklists.md
@docs/workflows/troubleshooting.md
@docs/cross-cutting/sound-design.md
@docs/cross-cutting/anchored-toolchain.md
@docs/cross-cutting/artifact-layout.md
@docs/cross-cutting/source-derived-sonic-mix-profile.md
@docs/pipeline/scoring_and_selection/README.md
@docs/pipeline/assembly_and_mux/README.md
@docs/pipeline/publishing/README.md
@docs/pipeline/audio_editing/README.md
@docs/prompts/README.md
@docs/prompts/analysis-stage-matrix.md
@src/interview_mux/pipeline.py (FLOW1_ORDER, FLOW2_ORDER, FLOW3_ORDER, ANALYSIS_ORDER)
@docs/build-out/stage-registry.md

Update so docs match code today:
- pipeline.md: mix_flow1/mix_flow2 canonical; assembly_preview shipped; Flow 3 shipped; remove "v1 gap" speech-only mux
- docs/README.md + INDEX.md: implementation status reflects shipped mix + flow3; source_acoustic_profile shipped (082)
- operator-stage-checklists.md: mix_flow* reality (VO + SFX in master.wav); assembly_preview + SDP path; remove "until BUILD-065/069"
- troubleshooting.md: replace speech-only expected rows with mix-path diagnostics (missing VO/SFX assets, edl, SDP cues)
- sound-design.md: title/status → shipped; link Wave 5 section to README#wave-5--coherent-sound-design-done; source_acoustic_profile shipped
- anchored-toolchain.md: pydub/mix engine → shipped (BUILD-065)
- artifact-layout.md: show_description.md export shipped (BUILD-046)
- scoring_and_selection/README.md: assembly_preview + publishing_flow3 shipped
- assembly_and_mux/README.md: canonical stage ids mix_flow1/mix_flow2; mux_flow* legacy alias only
- prompts/README.md + analysis-stage-matrix.md: sound_design/theme-palettes and flow plan stages shipped
- audio_editing/README.md: NLE → ranking/EDL shipped (068); keep crossfade notes as target if not in code

Link to podcast-quality-roadmap.md and stage-registry.md instead of duplicating mix tables.
Follow @docs/build-out/doc-maintenance.md. No operator-facing strings outside gui_log policy.
```

**Done when:** `rg -i "speech-only|until Wave 5|until BUILD-065|until BUILD-067|v1 gap" docs/pipeline.md docs/README.md docs/INDEX.md docs/workflows/ docs/pipeline/ docs/cross-cutting/sound-design.md docs/cross-cutting/anchored-toolchain.md` returns no stale hits (historical ticket-specs/build-out archive text excluded).

---

## Command 3 — Artifact schema validation at boundaries (**done**)

Shipped — see [json-schema-coverage.md](../cross-cutting/json-schema-coverage.md) validator table, `prompt_validation.py`, `tools/verify_edl.py`.

Wire JSON Schema checks where artifacts are **written or consumed**, without changing mux semantics.

**Agent prompt:**

```text
Implement artifact schema validation at consume/save boundaries only.

Read:
@docs/cross-cutting/json-schema-coverage.md
@docs/cross-cutting/artifact-layout.md
@docs/cross-cutting/json-schemas/artifacts/edl_flow1.schema.json
@docs/cross-cutting/json-schemas/source_acoustic_profile.schema.json
@docs/cross-cutting/json-schemas/analysis_state.schema.json
@src/interview_mux/prompt_validation.py
@src/interview_mux/stages/assembly_flow1.py (edl_flow1, mix_flow1)
@src/interview_mux/web/server.py (artifact PUT paths)

Deliver:
1. prompt_validation: validate_edl_flow1(), validate_source_acoustic_profile(), validate_analysis_state() (or reuse pattern from validate_sound_design_plan)
2. Call validate_edl_flow1 after edl_flow1 writes edl.json; fail stage with ctx.log() path errors (no silent continue)
3. GUI artifact save: validate analysis_state + source_acoustic_profile when paths match
4. Add minimal schemas if missing: run_meta.schema.json, transcript/corrections.schema.json, ingest/checksums.schema.json — validate on write only
5. Optional CLI: tools/verify_edl.py --run-id <exec_id> (non-zero on fail; no pytest in this command)

Update json-schema-coverage.md matrix (validator wired: yes/no per artifact).
Update artifact-layout.md schema? column for any new schemas.
Update stage-registry.md drift watchlist — close EDL validator row when wired.
Do not add default pipeline stages.
```

**Done when:** Invalid `edl.json` fails `edl_flow1` with operator-visible log; coverage doc lists validator wiring; optional `tools/verify_edl.py` runs on a fixture exec.

---

## Command 4 — Flow 1 narrative QA validators (**done**)

Shipped — `narrative_qc.py`, `tools/validate_narrative.py`, `gates.py` strict hooks.

Automate the **Flow 1 narrative** checks in [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md) (coverage topics, non-empty chapters).

**Agent prompt:**

```text
Implement Flow 1 narrative QA validators — tooling + gate hook, not a new LLM stage.

Read:
@docs/cross-cutting/evaluation-metrics.md (Flow 1 narrative section)
@docs/build-out/stage-registry.md (topic_coverage_audit, narrative_arc_plan, full_master_ranking)
@docs/pipeline/scoring_and_selection/README.md
@src/interview_mux/gates.py
@src/interview_mux/stages/analysis_flow1_extended.py
@src/interview_mux/stages/selection_flow1.py
@docs/cross-cutting/artifact-layout.md (narrative_plan.json, selection.json shapes)

Deliver:
- New module e.g. interview_mux/narrative_qc.py with validate_flow1_narrative(ctx) -> list[str] errors
- Rules: every content_brief.topics[] mapped in coverage_audit or documented exclude; no chapter with zero segments in selection.json
- tools/validate_narrative.py --run-id <exec_id> prints errors, exit 1 on fail
- Optional: gates.py warns (or blocks when config narrative_qc.strict: true) before full_master_ranking or edl_flow1
- ctx.log() summary event narrative_qc_pass / narrative_qc_fail
- Document in operator-stage-checklists.md, evaluation-metrics.md, scoring_and_selection/README.md
- podcast-quality-roadmap.md: narrative validators row → partial/shipped as appropriate

No pytest required for this command.
```

**Done when:** CLI reports failures on a deliberately bad fixture run; pass on a good `data/run_201`-style layout; checklist and evaluation-metrics document the command.

---

## Command 5 — G1.5 post-listen pass/fail GUI — **Shipped**

Post-listen Pass/Fail panels on `sfx_prompt_craft` and `mmaudio_sfx_flow*`; `GET …/runs/{id}` includes `sfx_generated_assets`.

**Agent prompt:**

```text
G1.5 post-listen GUI only — wire existing listen-result API.

Read:
@src/interview_mux/web/server.py (post_sfx_listen_result, run_meta.sfx_listen_results)
@src/interview_mux/web/static/app.js (mmaudio_sfx_flow1/2 panels, G1.5 craft panel)
@docs/cross-cutting/local-audio-stack.md
@docs/workflows/gui-surface-map.md
@docs/workflows/api-reference.md
@docs/workflows/operator-stage-checklists.md

Deliver:
- After operator plays sound_design/assets/{asset_id}.wav (or flow sfx mirror), show Pass / Fail + optional note
- POST /api/runs/{run_id}/sfx-prompts/listen-result with { asset_id, result, note? }
- Surface run_meta.sfx_listen_results[] in craft or SFX stage panel (read-only history)
- ctx.log via server already exists — ensure GUI refreshes log panel
- Update g15-and-value-analysis-execution.md: Command 5 shipped
- Update local-audio-stack.md: replace "GUI (planned)" steps with shipped panels + post-listen flow
- Add Pass/If fail rows to operator-stage-checklists.md for post-listen (advisory)

Respect g1_5_require_prompt_approval — post-listen is advisory unless product adds a hard gate later.
No new pipeline stages.
```

**Done when:** Manual GUI path: listen → pass/fail → entry in `run_meta.json` and `gui_log.jsonl`; api-reference + gui-surface-map + mmaudio-prompt-tuning.md document the flow.

---

## Command 6 — Optional: auto-extract value features after analysis (**shipped**)

Hook in `understanding.run_content_context` when `value_analysis.enabled` and `value_analysis.auto_extract_after_content_context` (shipped default **on**). Implementation: `src/interview_mux/value_analysis/extract.py`.

**Agent prompt:**

```text
Optional value-analysis auto-extract — config-gated only.

Read:
@src/interview_mux/value_analysis/config.py
@tools/extract_value_features.py
@src/interview_mux/stages/understanding.py (content_context)
@config/app.defaults.json
@docs/cross-cutting/config-keys.md
@docs/pipeline/value-analysis/README.md
@docs/roadmap/future-proofing.md
@docs/build-out/g15-and-value-analysis-execution.md

Deliver:
- New flag value_analysis.auto_extract_after_content_context (default false)
- After content_context stage completes successfully, if enabled, call extract_transcript_features (+ audio if audio_features flag) and write understanding/value_features.json
- ctx.log() value_features_extracted with profile list
- Do NOT add stages to default pipeline.py order; hook inside existing stage or analysis_memory helper only when flag on
- Update config-keys.md, future-proofing.md shipped table, value-analysis/README.md, g15 guide (auto-extract row)

Explicitly do not enable flags in defaults — local operator opt-in only.
```

**Done when:** With flags on in local config, a run gets `value_features.json` without manual CLI; with flags off, behavior unchanged; config-keys documents the new flag.

---

## Command 7 — Value-analysis spike documentation sprint (**done**)

See [spike-results-and-winners.md](../pipeline/value-analysis/spike-results-and-winners.md) and `tests/fixtures/value_analysis/spike_*.json`.

Fill [spike-results-and-winners.md](../pipeline/value-analysis/spike-results-and-winners.md) for TBD sections using existing CLIs (no new ML deps).

**Agent prompt:**

```text
Value-analysis spike documentation sprint — docs + fixture scorecards only.

Read:
@docs/pipeline/value-analysis/phase3-spike-framework.md
@docs/pipeline/value-analysis/spike-results-and-winners.md
@docs/pipeline/value-analysis/sections/
@docs/pipeline/value-analysis/value-metrics-library.md
@docs/pipeline/value-analysis/tools-not-in-repo-landscape.md
@tools/run_value_spike.py
@tests/fixtures/value_analysis/spike_flow1_sound.json

For each TBD row (shared-ingest through cross-orchestration):
1. Add tests/fixtures/value_analysis/spike_<section>.json with 2–3 candidates (include "prompt-only" baseline)
2. Run tools/run_value_spike.py with listener-first and idea-first profiles; paste ranked table into spike-results-and-winners.md
3. Record Promote / Park / Kill one-liner per section
4. Cross-link value-metrics-library.md and section READMEs where a metric or tool won

Do not wire spikes into pipeline.py. Do not add SSL/CLAP dependencies in this command.
```

**Done when:** Every section row in spike-results has a date, profiles tested, and top candidate; at least three new fixture JSON files under `tests/fixtures/value_analysis/`.

---

## Command 8 — Moonshot spike: SSL idea-density curves (**optional — not started**)

Only remaining item in this queue. Proceed only if spike-results recommend SSL for a section.

Time-boxed **T0** prototype per [future-proofing.md](../roadmap/future-proofing.md). Only proceed if Command 7 recommends SSL for a section.

**Agent prompt:**

```text
Optional T0 spike — SSL sliding-window idea-density proxy for value_features (feature-flagged).

Read:
@docs/pipeline/value-analysis/sections/shared-ingest-transcribe.md
@docs/pipeline/value-analysis/moonshot-model-families.md (Family 1)
@docs/cross-cutting/anchored-toolchain.md
@docs/cross-cutting/config-keys.md
@src/interview_mux/value_analysis/features_audio.py

Constraints:
- New dependency only via requirements.txt + requirements.lock + pip-audit pass
- Pin versions; document in anchored-toolchain.md
- Output: optional profile ssl_density in value_features.json when value_analysis.ssl_features: true (default false)
- Implement in features_audio.py or new features_ssl.py called from extract_value_features.py only
- Record spike outcome in spike-results-and-winners.md
- Do NOT add default pipeline stage

If spike shows no lift vs existing audio profile metrics, document Park and stop — do not merge heavy deps.
```

**Done when:** Either a flagged extractor profile works on `ingest/normalized.wav`, or spike-results documents **Park** with rationale; lockfile + config-keys updated only if promoted.

---

## Command 9 — Repository definition of done (manual sign-off + final doc grep)

Close unchecked DoD items and run a **repo-wide stale-doc grep** so nothing outside Commands 1–2 still misstates shipped behavior.

**Agent prompt:**

```text
Repository definition-of-done sign-off — documentation and operator checklist only.

Read:
@docs/build-out/implementation-guide.md (Definition of done)
@docs/build-out/steps-forward.md (Definition of done)
@docs/build-out/stage-registry.md
@docs/build-out/repository-map.md
@docs/workflows/smoke-test.md
@docs/workflows/operator-stage-checklists.md
@docs/workflows/gui-surface-map.md
@docs/workflows/api-reference.md
@AGENTS.md
@docs/INDEX.md
@src/interview_mux/pipeline.py
@src/interview_mux/web/stages.py

Deliver:
1. Checklist doc docs/build-out/definition-of-done-signoff.md with manual steps for:
   - ASSETS E2E (picker, exec_*, resume)
   - G2 flow1/2/3 CLI + GUI
   - flow1/2 master includes SFX mix (listen)
   - pre-clean offers at checkpoints (never auto)
   - stage-registry ↔ pipeline.py ↔ web/stages.py parity
   - smoke-test.md sections for all three flows
2. Mark implementation-guide and steps-forward checkboxes [x] only for items verified against current code (cite file paths)
3. Clear or update repository-map.md gap table rows that are fully shipped
4. Repo-wide grep and fix any remaining stale claims in docs/:
   rg -i "speech-only|until Wave 5|until BUILD-065|until BUILD-067|v1 gap|flow1 \\| flow2 only|\\(planned\\)" docs/
   Exclude: historical shipped prompts in steps-forward.md body, ticket-specs acceptance history, value-analysis TBD rows not yet run in Command 7
5. AGENTS.md + INDEX.md: link definition-of-done-signoff.md; hub status matches docs/README.md
6. smoke-test.md note: "automated pytest optional; use signoff doc for release candidate"

No code changes unless a checklist item reveals a real bug — then file a one-line pointer to which Command 3–5 fixes it.
```

**Done when:** `definition-of-done-signoff.md` exists; implementation-guide DoD reflects reality; repository-map has no stale gap rows; repo-wide grep returns no stale operator-facing claims (per exclusions above).

**Status:** Shipped — see [definition-of-done-signoff.md](./definition-of-done-signoff.md).

---

## Command 16 — BUILD-SFX-17 Holistic gap closure (**shipped**)

**Goal:** Close remaining SFX audit gaps — sonic-context wiring, test matrix, operator docs, regression examples.

**Scope:** WS7–WS10 of holistic SFX gap closure plan (EDL audit input, export headers, listen API, 9-scenario tests, sign-off docs, example corpus).

**Verify:**

```bash
pytest tests/test_sonic_context.py tests/test_sound_design_scenario.py tests/test_sfx_gates.py tests/test_stage_parity.py -q
```

**Done when:** BUILD-SFX-17 block in [ticket-specs.md](./ticket-specs.md) checked; [definition-of-done-signoff.md](./definition-of-done-signoff.md) 9-scenario matrix present.

**Status:** Shipped.

---

## Commands 10–15 — BUILD-084 Quality-first LLM harness (**shipped**)

| Command | Scope | Status |
|---------|-------|--------|
| 10 | Merge/persist gating, collate volley, tests | Shipped |
| 11 | Volley retries, accepted summaries, shard audit files | Shipped |
| 12 | `llm_stage_routing`, `llm_shard_plans`, expanded decompose | Shipped |
| 13 | `llm_specialists`, value orchestration investigations | Shipped |
| 14 | Envelope/nle schemas, context_index, narrative QC queue | Shipped |
| 15 | Docs, GUI `/llm-routing`, `test_llm_harness_084.py` | Shipped |

Modules: `llm_stage_routing.py`, `llm_shard_plans.py`, `llm_routing_debug.py`, `llm_specialists.py`. See [ticket-specs.md](./ticket-specs.md) BUILD-084.

---

## Related

- [gap-closure-agent-commands.md](./gap-closure-agent-commands.md) — gap-closure Agent queue (GC-00–GC-D1 shipped; Phase 6 follow-up)  
- [steps-forward.md](./steps-forward.md) — historical backlog + shipped Agent prompts  
- [g15-and-value-analysis-execution.md](./g15-and-value-analysis-execution.md) — G1.5 / VA track (mostly shipped)  
- [implementation-guide.md](./implementation-guide.md) — phased build plan  
- [ticket-specs.md](./ticket-specs.md) — acceptance for completed BUILD ids  
- [doc-maintenance.md](./doc-maintenance.md) — docs to update per PR  
