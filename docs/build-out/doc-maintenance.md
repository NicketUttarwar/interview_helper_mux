# Documentation maintenance

Every code PR that changes behavior must keep docs authoritative. Agents: run this checklist before marking a BUILD ticket done.

**Policy source (always-on in Cursor):** `.cursor/rules/interview-helper-mux.mdc` — build-out workflow, hard constraints, gates, logging, v1 honesty, doc obligations. Do not duplicate those blocks in other docs; link instead.

---

## Always update (same PR as code)

| Change type | Update |
|-------------|--------|
| New / renamed pipeline stage | [stage-registry.md](./stage-registry.md), `pipeline.py` comment if needed, `docs/pipeline/<area>/README.md`, [operator-stage-checklists.md](../workflows/operator-stage-checklists.md) |
| Optional quality stage wiring (e.g. `audio_preclean`) | [operator-gates.md](../workflows/operator-gates.md) quality offers table, `web/stages.py`, and stage README under `docs/pipeline/` |
| Stage I/O path change | [artifact-layout.md](../cross-cutting/artifact-layout.md), [json-schema-coverage.md](../cross-cutting/json-schema-coverage.md), json-schemas if applicable |
| LLM artifact generation / validation / gap-fill | [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md), `artifact_completeness.py`, `artifact_writes.py`, `tools/codegen_zod_schemas.py`, [gui-surface-map.md](../workflows/gui-surface-map.md) |
| Shared analysis scaffolds (e.g. SDP init) | [artifact-layout.md](../cross-cutting/artifact-layout.md), [json-schema-coverage.md](../cross-cutting/json-schema-coverage.md), `json-schemas/*.schema.json`, [stage-registry.md](./stage-registry.md) |
| Sound design palette stage (BUILD-061) | `pipeline.py` (`ANALYSIS_ORDER`), `web/stages.py`, [stage-registry.md](./stage-registry.md), [operator-stage-checklists.md](../workflows/operator-stage-checklists.md), `artifacts/sound_design_palettes_artifact.schema.json` |
| ASSETS / run discovery / resume | [assets-and-executions.md](../cross-cutting/assets-and-executions.md), [full-application-flow.md](./full-application-flow.md), [gui-surface-map.md](../workflows/gui-surface-map.md) |
| Source audio hash / run id format | [artifact-layout.md](../cross-cutting/artifact-layout.md), [assets-and-executions.md](../cross-cutting/assets-and-executions.md), [run_meta.schema.json](../cross-cutting/json-schemas/run_meta.schema.json), `source_audio_hash.py` |
| Stage execution reuse | [stage-execution-reuse.md](../workflows/stage-execution-reuse.md), [idempotent-runs.md](../workflows/idempotent-runs.md), [operator-stage-checklists.md](../workflows/operator-stage-checklists.md), `stage_execution_reuse.py` |
| Per-stage write approval | [gui-surface-map.md](../workflows/gui-surface-map.md), [api-reference.md](../workflows/api-reference.md), [config-keys.md](../cross-cutting/config-keys.md), `write_staging.py` |
| New GUI panel or route | [gui-surface-map.md](../workflows/gui-surface-map.md), [api-reference.md](../workflows/api-reference.md), `web/stages.py`, `frontend/src/components/` |
| Frontend / Vite build output | Rebuild `./scripts/build_gui.sh`; commit `src/interview_mux/web/static/index.html` + `static/assets/*` (not ignored — see `/ASSETS/` anchor in `.gitignore`) |
| GUI UX / operator shell change | [gui-surface-map.md](../workflows/gui-surface-map.md), [operator-journey.md](../workflows/operator-journey.md), [operator-flow-audit.md](../workflows/operator-flow-audit.md), [troubleshooting.md](../workflows/troubleshooting.md) |
| Gate or quality offer | [operator-gates.md](../workflows/operator-gates.md), checklists, [podcast-quality-roadmap.md](../cross-cutting/podcast-quality-roadmap.md) if offer checkpoint |
| LLM prompt copy | `docs/prompts/**/*.system.txt`, [analysis-stage-matrix.md](../prompts/analysis-stage-matrix.md), examples under `prompts/_shared/examples/`; gap-fill line when stage writes artifacts |
| LLM guidance / quality tiers | [llm-guidance-program.md](../cross-cutting/llm-guidance-program.md), [stage-quality-scorecard.md](../cross-cutting/stage-quality-scorecard.md), [LLM-ANALYSIS-ARCHITECTURE.md](../../LLM-ANALYSIS-ARCHITECTURE.md) §18–20 |
| Placement QA (post-SFX) | [post-generation-placement.md](../cross-cutting/post-generation-placement.md), `placement_qa.py`, `sound_design.placement_qa_enabled` in [config-keys.md](../cross-cutting/config-keys.md) |
| LLM call export CLI | `tools/export_llm_calls.py`, [llm-call-record-framework.md](../cross-cutting/llm-call-record-framework.md), [gui-surface-map.md](../workflows/gui-surface-map.md) Debug tab |
| LLM routing debug API | `GET /api/runs/{id}/llm-routing`, `llm_routing_debug.py`, [api-reference.md](../workflows/api-reference.md), [llm-orchestration.md](../cross-cutting/llm-orchestration.md) |
| Volley memory / `STAGE_PLANS` | **Code source of truth:** `STAGE_PLANS` in `context_volley.py`. Sync table in [context-padding.md](../cross-cutting/context-padding.md). CI: `python tools/audit_stage_plans_doc.py`. Index: [analysis-memory.md](../cross-cutting/analysis-memory.md) |
| Golden envelope fixtures | `tests/fixtures/llm_envelopes/`, `tests/test_llm_envelope_fixtures.py`, `deterministic_lint.py` |
| Config / secrets key | [config-keys.md](../cross-cutting/config-keys.md), `config/templates/secrets.env.example` |
| Narrative QC / EDL validators | [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md), [json-schema-coverage.md](../cross-cutting/json-schema-coverage.md), `tools/validate_narrative.py`, `tools/validate_edl.py`, `tools/verify_edl.py` |
| Value analysis hook | [value-analysis/README.md](../pipeline/value-analysis/README.md), [config-keys.md](../cross-cutting/config-keys.md) |
| Dependency pin | `requirements.txt`, `requirements.lock` (`pip-compile requirements.txt -o requirements.lock`), [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md), [anchored-requirements.lock](../cross-cutting/anchored-requirements.lock); re-run `./tools/check_prerequisites.sh` |
| Ticket shipped or partial | [README.md](./README.md), [ticket-specs.md](./ticket-specs.md) checkboxes, [repository-map.md](./repository-map.md) gap table |
| Closed doc↔code gap | Remove or update row in [repository-map.md](./repository-map.md); adjust [steps-forward.md](./steps-forward.md) if backlog item complete |

---

## Update when scope warrants

| Change type | Update |
|-------------|--------|
| New BUILD ticket | [README.md](./README.md) wave table, [ticket-specs.md](./ticket-specs.md), [stage-registry.md](./stage-registry.md) if stage involved |
| Priority shift | [steps-forward.md](./steps-forward.md) (keep Agent prompt blocks in sync if step scope changes) |
| New module / top-level path | [repository-map.md](./repository-map.md) |
| Smoke path change | [smoke-test.md](../workflows/smoke-test.md), [SETUP.md](../../SETUP.md) |
| Master QA threshold or failure behavior | [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md), [smoke-test.md](../workflows/smoke-test.md), [testing-and-verification.md](./testing-and-verification.md) |
| Troubleshooting symptom | [troubleshooting.md](../workflows/troubleshooting.md) |
| Sound / mix behavior | [sound-design.md](../cross-cutting/sound-design.md), [assembly_and_mux/README.md](../pipeline/assembly_and_mux/README.md) |

---

## Do not duplicate

| Topic | Canonical location |
|-------|-------------------|
| Python / ffmpeg / API versions | [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md) |
| Operator logging | `.cursor/rules/interview-helper-mux.mdc` |
| Per-stage Pass / If fail | [operator-stage-checklists.md](../workflows/operator-stage-checklists.md) |
| HTTP request bodies | [api-reference.md](../workflows/api-reference.md) |
| Ticket acceptance | [ticket-specs.md](./ticket-specs.md) |

Link instead of copying tables across files.

---

## Optional / out of default path

| Area | Rule |
|------|------|
| [value-analysis/](../pipeline/value-analysis/) | Update only when running spikes; not required for core ship |
| [future-proofing.md](../roadmap/future-proofing.md) | Guardrails only; no implementation promise |

---

## PR self-check (copy for description)

```markdown
- [ ] stage-registry.md (if stage)
- [ ] operator-stage-checklists.md (if operator-visible)
- [ ] gui-surface-map + api-reference (if GUI/API)
- [ ] artifact-layout / schemas (if I/O)
- [ ] prompts + analysis-stage-matrix (if LLM)
- [ ] build-out README + ticket-specs + repository-map gaps (if BUILD ticket)
- [ ] ctx.log() for new operator strings
- [ ] smoke-test section still accurate
- [ ] requirements.lock + anchored-requirements.lock mirror (if deps; BUILD-010)
```

---

## Related

- [implementation-guide.md](./implementation-guide.md) — per-ticket workflow
- [testing-and-verification.md](./testing-and-verification.md) — verification steps
