# Possibility Map — mastering_research_rollup

brain: 0.2.0 | discovery_status: complete  
code_is_king: true | prior_exec: ignored_by_default

## Tag legend

`IN_CODE` | `DOC_ONLY_UNVERIFIED` | `CODE_DOC_CONFLICT` | `UNKNOWN` | `FULL_AUTO_REGRESSION_RISK`

## §5.0 Index

- tier: process / body deterministic (+ may re-invoke routing LLM if enabled)
- primary: `mastering/research/rollup.json` + `mastering/research_dossier.json` (same dossier payload)
- module: `mastering_research.py::run_mastering_research_rollup` → `run_research_rollup`
- upstream: waves.json hard (contract); body re-runs waves + routing regardless
- consumers: shape agenda/candidates/synthesize/confirm — `IN_CODE` `RESEARCH_CONSUMER_STAGES`
- gate: none | thrash: shape-core thin latch (A-01) | LLM: routing only if `mastering.research.llm.enabled`

## 1. Input completeness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| all hard present | Re-route + re-wave + write dossier/rollup; heal | IN_CODE | `run_research_rollup` |
| hard missing waves.json | Still rebuilds waves from probes | CODE_DOC_CONFLICT | body vs contract hard |
| soft missing | Thin fields in dossier | IN_CODE | |
| hollow dossier | HM-1 schema incompleteness | IN_CODE | `_mastering_schema_hollow_incompleteness` |
| shape-core majority thin / required missing | `shape_core.ready=false`; consumers refused late | IN_CODE | `_shape_core_status_from_fields` / `_research_thin_late_refuse` |
| stale thin dossier after evidence lands | Rollup marked incomplete until re-run | IN_CODE | `research_dossier_shape_core_stale` |

## 2. Upstream freshness

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| producer done | Proceed; may re-probe | IN_CODE | |
| producer invalidated | Re-run | IN_CODE | |
| live vs dossier drift | Stale latch forces rollup resume | IN_CODE | `research_dossier_shape_core_stale` |

## 3. Partial-accel gate posture

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A | No gate | IN_CODE | |

## 4. Execution outcomes

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| clean success | dossier + rollup.json; heal | IN_CODE | |
| research.llm on + OpenAI fail | Stub routing (`llm_failed`); still rollup | IN_CODE | `_sequential_stub_routing` |
| research.llm off (default) | Stub routing mode `off` | IN_CODE | `research_llm_enabled` default False |
| done while shape-core thin + Shape about-to-bind | Incomplete refuse on rollup | IN_CODE | `_research_thin_late_refuse` |
| identical halt | No local fingerprint | IN_CODE | |

## 5. Side effects

- Writes: `mastering/research_dossier.json`, `mastering/research/rollup.json`, field reports, possibly routing — `IN_CODE`
- Consumers refused on thin core: shape + missing_framing + gap_framing — `IN_CODE`
- Heal pin: `heal_routing` → `mastering_research_rollup` for shape-core — `IN_CODE`

## 6. Complexity traps

- OpenAI: optional routing only (`mastering.research.llm.enabled` default **false**)
- A-01 thin/stale latch complexity — `IN_CODE` stage_completion
- Dual write dossier + rollup same payload — `IN_CODE`
- Local heavy ML: N/A

## 7. Contract honesty

| Declared | Actual (code) | Tag |
|----------|---------------|-----|
| hard waves.json | Rebuilt anyway | CODE_DOC_CONFLICT |
| outputs rollup + dossier + glob | Matches (+ rewrites routing) | IN_CODE |
| consumers shape/synthesize/confirm | Also missing_framing/gap via RESEARCH_CONSUMER | CODE_DOC_CONFLICT |

## 8. External service variance

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| N/A when research.llm false (default) | Stub routing | IN_CODE | `config/app.defaults.json` |
| if llm enabled: fail ≤2 → stub | Fail-open stub | IN_CODE | `run_research_routing` max_attempts=2 |

## 9. Full-auto / defaults path (REQUIRED)

| Case | Outcome | Tag | Code pointer |
|------|---------|-----|--------------|
| Full-auto + defaults | Completes with advisory stub routing; thin core may block Shape/gap | IN_CODE | `mastering.research.llm.enabled=false` |
| human stall? | No | IN_CODE | |
| GUI-only? | No | IN_CODE | |
| landmine | Thin shape-core at Pass1 pins consumers until evidence/probes ready | IN_CODE | A-01 |
| partial-only fix risk | Forcing soft-success on thin core would poison Shape — `FULL_AUTO_REGRESSION_RISK` if removed | IN_CODE | |

## Flags (§5.5)

| flag | default | site | effect |
|------|---------|------|--------|
| `mastering.research.llm.enabled` | false | `mastering_plan_loader.research_llm_enabled` | OpenAI routing vs stub |
| `mastering.research.routing.mode` | advisory | app.defaults | routing mode claim |

## TEST_GAP

- End-to-end stale-dossier clear under seed walk (partial coverage in research thin latch tests)
- Contract consumer list vs RESEARCH_CONSUMER_STAGES

## DoD threats

- [x] 1 Progression  [x] 2 Honesty  [ ] 3 Stalls  [ ] 4 OpenAI  [x] 5 Defaults  [ ] 6 Ship bar  [x] 7 Cross-stage

## Open questions

1. Keep A-01 refuse for gap stages when gap_fill skipped (already exempt) — any other exemptions?

## discovery_status

`complete`
