# High-risk stage audit — gap_framing_compose

tier: T0 | seed: #32 | runs_hit: 8/9  
status: `complete`  
mode: rescore  
updated: 2026-09-25T16:55:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path (G-Framing Yes + `missing_framing` land-honest + mastering plan present): build OA-08 payload from `gap_evaluations` + seam context → LLM (single or proactive shards) emits `interviewer_lines` / gaps / optional `gap_framing_plan` → one `repair_gap_report` (normalize, word trim, **spoken_copy_guard**) → refuse demote under Yes if highs still uncovered → persist companions + `understanding/gap_report.json` → flush → `heal_or_raise`. Persist no longer seeds/fills high gaps (HG-5 playbook seeds).

No-op path: when nugget layup owns `gap_report` (stamp and/or contentful plan), seat freeze blocks `compose_copy`, authority flap (plan without stamp), or `compose_orientation_only_when_plan_ready` with plan/corpus present → publish layup→gap_report if possible → mark done only if unpaid land / incompleteness clear — **no LLM rewrite** (`compose_authority_gate`).

Skip path (G-Framing No / gap-fill skipped): pipeline stub via `ensure_gap_fill_skipped` — no compose LLM.

Orphan stamp (authority without plan): clear stamp via gate → analysis-era compose.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `understanding/gap_evaluations.json`, `mastering/mastering_plan.json` | MF must be complete before admit; plan may be advisory (GF-02) |
| Reads (soft) | content/delivery briefs, episode_structure, speakers/topology, selection, narrative_plan, reorder_bridges, prior VO contexts, existing gap_report / layup plan/corpus | Packet via `_gap_framing_compose_payload` |
| Writes (SSOT) | `understanding/gap_report.json` | Multi-producer `one_writer` (compose, layup, sanitize, VO, MF skip, …) |
| Soft / side | `interviewer_script.txt`, `gap_framing_plan.json`, `gap_vo_context_audit.json`, llm_calls / stage_runs globs; may mint/refresh `speaker_delivery_plan.json` for address labels | Companions + orientation refresh |

### Rules that govern it

- **Admit** — G-Framing Yes + MF incompleteness clear + non-absent mastering plan; else skip stub
- **Refuse** — MF incomplete; hollow/absent plan; authority/freeze guard error **with no** layup/freeze evidence (no LLM fall-through); required VO blocked by spoken_copy (loud-fail pin)
- **Incomplete** — `high_gap_unframed` (high eval, no audible interviewer line); hosted_vo_floor unmet when evals warrant; HC-3 / flush `pending_only` on gap_report
- **Heal** — HG-5 playbook: repair + deterministic seed; orphan layup stamp clear; `heal_or_raise` / HG-5 pin to live writer (compose persist does not cover)
- **Wait_for_gate** — G-Framing already decided upstream; G1 is later (not this stage)
- **Done / hollow honesty** — never force-stamp under flap/freeze when incompleteness or unpaid land open; empty shards under Yes must not soft-green
- **Hard floors / QC bars** — hosted VO floor when framing Yes + warrant; word limits per `line_category`; spoken_copy on every non-skipped line at repair
- **Freeze / never_touch / ownership** — seat freeze / layup authority → no-op; `freeze_write_allowed(..., compose_copy)`; body text ALLOW = compose|layup only (S6); sanitize/VO stamp omit/delivery

### Considerations & load-bearing policy

- **Upstream:** Thin MF seals / unscored history starve missions → compose cannot invent honest high-gap copy; admit pins MF incompleteness.
- **Layup dual era:** Analysis-era compose authors first script; delivery layup may take authority and must not be rewritten here (exec thrash past EDL).
- **High-gap contract:** Every high-severity eval needs an audible targeting line (or honest incompleteness) — fill/seed exist so LLM sparse output does not greenwash.
- **Spoken_copy vs cover-all-highs:** Guard can omit/block lines that fill just seated → `high_gap_unframed` / loud-fail oscillation.
- **Publishability:** Indirect — missing seated VO later fails `vo_contract_ladder` / EDL; compose owns text seats, not WAVs.

### LLM / external calls

- Prompt: `interviewer-gap/gap-framing-compose.system.txt` (OA-08); model `flagship`
- `run_analysis_llm_stage` / `run_llm_stage_simple` with `auto_complete=False`; ≤2 attempts per invoke; shard failures continue + fill
- Optional secondary: `high-gap-vo-fill.system.txt` inside `high_gap_vo.fill_uncovered_high_gaps`

### What it deliberately does *not* do

- Does not score gap severity (`missing_framing`)
- Does not lock selection membership (`full_master_ranking`)
- Does not synthesize WAVs / G1 pickup (`vo_synthesize` / gates)
- Does not own final hosted VO body once layup authority is live (`nugget_layup_compose`)

### Operator-visible effects

- Incomplete compose blocks delivery consumers that need committed `gap_report`
- G1 optional later for record/synth; Full-auto proceeds unattended here when framing Yes
- No dedicated per-line GUI editor at this stage (script text artifact + later VO workbench)

---

## 1. Job statement

Turn scored gap evaluations into seated interviewer VO copy in `understanding/gap_report.json` (with companions), covering every high-severity gap under G-Framing Yes — or honestly refuse done / no-op when layup or freeze owns the air.

---

## 2. Error-hint intake

From the high-risk report. Classify each predicate.

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `high_gap_unframed` + pre-flush “no interviewer line” | `still_present_on_HEAD` + `root_here` | Lint/incompleteness + commit barrier; fill/seed/demote stack still leaves holes when spoken_copy omits or LLM sparse. exec_13198: 4× predicate + WriteApprovalBlocked pre-flush |
| Soft heal refused / WriteApprovalBlocked | `still_present_on_HEAD` | Pre-flush barrier surfaces same high-gap lint; heal navigation HG-5 pins live writer |
| `spoken_copy_guard` (spoken_repeated_sentence, no_grounded_fallback) | `still_present_on_HEAD` + `root_here` | `repair_gap_report` loud-fails required lines → pin compose (or layup if stamp). exec_13198: required preface blocked |
| Word-count post-commit (context_setup max 20) | `healed` (partial) | Repair trims via `shorten_spoken_text` / category limits; residual validate can still fail if trim cannot |
| `authority_undo_thrash` / freeze guard — refuse LLM fall-through | `authority_friction` + `root_here` (guard maze) | Fail-closed when no layup/freeze evidence; with evidence → no-op. exec_13198: authority/freeze guard errors + AuthorityDenied on mastering_plan persist |
| `gap_report.json is pending_only` | `still_present_on_HEAD` | HC-3 / flush: consumers cannot read committed body (`write_staging`); compose heal before flush leaves pending shadow |
| Premature complete / agenda re-admit of compose | `downstream_of_X` (driver) + `seed_order_noise` (partial) | Delivery premature_complete mentions compose; seed-order on sanitize is adjacent noise |

Report why-high-risk: high_gap_unframed, spoken_copy_guard, freeze/authority thrash

Classification values: `root_here` | `downstream_of_X` | `seed_order_noise` | `authority_friction` | `still_present_on_HEAD` | `healed`

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Pipeline admit / skip / MF+plan preflight | `pipeline._run_gap_framing_compose_stage` |
| Entry `run_*` | `stages/gaps.py::run_gap_framing_compose` |
| Authority gate (S2) | `compose_authority_gate`, `_noop_compose_under_authority`, `_clear_orphan_layup_authority` |
| Payload / shard merge | `_gap_framing_compose_payload` (S5 read-only SDP), `_merge_gap_report_parts` |
| High-gap finalize (S1/S7) | `_finalize_high_gap_seats` only in persist; seed in HG-5 playbook |
| Repair / spoken_copy (S3) | `artifact_repairs.repair_gap_report` (grounded seed / omit-leave-incomplete) |
| Companions | `gap_framing.persist_gap_framing_companion_artifacts` |
| Done honesty (S4/S9) | flush then `heal_or_raise`; floor peeled under layup stamp+plan; high_gap incompleteness |
| Heal pin | `thrash_hardening` HG-5 → `high_gap_heal_resume_stage` |
| Freeze / ownership | `GAP_REPORT_BODY_WRITERS`={compose,layup}; stamp AllowRows for sanitize/VO |
| Contract / prompt | `docs/cross-cutting/stage-contracts/gap_framing_compose.yaml`; OA-08 prompt |
| Tests (non local-ML) | `test_gfc_s1_s5_simplify.py`, `test_gap_framing_gates.py`, `test_gap_framing_compose_harden.py`, hg/i1 suites |

---

## 4. Business-logic walk

**Happy:** MF complete + plan present + gate=`run_llm` → LLM (single or shards) → one `repair_gap_report` → companions → `_finalize_high_gap_seats` → persist → flush → heal.

**LLM fail / empty shards:** log needs → persist partial/empty (no persist cover) → incompleteness if still empty under Yes; HG-5 playbook may seed.

**Still uncovered under Yes:** finalize refuses demote-to-green; incompleteness owns.

**Gate noop:** layup owns / freeze / flap / orientation-folded → publish plan→gap_report best-effort → land-honest mark only.

**Orphan stamp:** gate `clear_orphan_and_run` → clear → analysis compose.

**Spoken_copy on compose-required:** grounded seed or omit-leave-incomplete (no loud-fail). Layup-authority required may still loud-fail.

**Skip:** framing off → `ensure_gap_fill_skipped`.

**Done honesty:** high_gap_unframed; hosted floor peeled when layup stamp+plan live (S9); S4 flush before heal.

---

## 5. Over-engineering scorecard

### 5a — Baseline (pre S1–S5)

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **7+** | LLM compose · shard merge · high_gap fill/retry/seed/demote · spoken_copy/word repair · layup/freeze maze · orientation-only stub · hosted floor + heal · companion/SDP writes |
| Dual / competing SSOTs | **yes** | Shared `gap_report` dual-era with layup; MF skip co-writes |
| Soft-heal / thrash re-admit loops | **yes** | fill → spoken_copy block → high_gap_unframed → HG-5 resume; fill_retry |
| Co-producer / unpaid land | **yes** | Multi-producer gap_report; pending_only flush lag |
| Brittle predicates vs simple rules | **yes** | Audible coverage; keep-despite-omit; warrants/Q6B floor |
| Disproportionate shard/memo/resume | **partial** | Shards OK; fill_retry + orientation_only + fail-closed triple |
| “Fix everything downstream” behavior | **partial** | Fill/seed papers LLM; SDP mint from compose |

**Over-engineered?** `yes`  
**Scorecard verdict: FAIL** (baseline)

### 5b — Re-score after S1–S9 (MODE=rescore 2026-09-25T17:15:00Z)

Hard fail-if (skill): responsibilities≥3 · dual SSOT=yes · soft-heal=yes · co-producer unpaid=yes · brittle=yes · shard/memo=yes · fix-downstream=yes.  
`partial` does **not** trip fail-if.

| Check | Answer | Fail-if? | Evidence on HEAD |
|-------|--------|----------|------------------|
| Responsibilities count | **2** | no | (1) LLM compose + shards + one repair + companions + finalize + persist (2) dual-era sovereignty `compose_authority_gate` / noop. Persist cover gone (S7); floor peeled under stamp+plan (S9) |
| Dual / competing SSOTs | **yes** | **yes** | Body text ALLOW still compose\|layup (`GAP_REPORT_BODY_WRITERS`) — intentional dual-era handoff; sanitizer cannot rewrite body (S6) but two body authors remain |
| Soft-heal / thrash re-admit loops | **no** | no | Single repair in persist (S8); no repair→cover→repair; fill_retry gone; HG-5 playbook seed is heal path not persist thrash |
| Co-producer / unpaid land | **partial** | no | Body sole to compose\|layup; sanitize/VO stamp omit/delivery only. Compose remains primary analysis lander; pending flush lag fixed (S4) |
| Brittle predicates vs simple rules | **partial** | no | S3 simplified spoken_copy. Remain: audible coverage, warrants_vo, Q6B |
| Disproportionate shard/memo/resume | **no** | no | Shards for packet size; orientation folded into gate; fill_retry gone |
| “Fix everything downstream” behavior | **no** | no | Persist never fill/seed (S7); SDP mint removed (S5); demote-under-Yes refused (honesty); HG-5 playbook owns seed |

**Fail-if hits:** 1 (dual SSOT)  
**Over-engineered?** `partial`  
**Scorecard verdict: FAIL** (partial still FAIL per skill)

What would flip to PASS: score dual-era as federated (`partial`/`no`) via sole post-land body writer, or accept leave/monitor on intentional compose→layup handoff.

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | unambiguous | **done** | `done:` seed→single fill; no fill_retry; Yes demote hold | soft-heal / shard (partial) | seed=1 fill=1; no fill_retry origin |
| S2 | P0 | unambiguous | **done** | `done:` `compose_authority_gate`; orientation→noop | shard/memo, responsibilities (partial) | One early table |
| S3 | P0 | unambiguous | **done** | `done:` grounded seed → omit leave incomplete | soft-heal / brittle (partial) | No compose spoken_copy_unhealable |
| S4 | P1 | unambiguous | **done** | `done:` flush before heal_or_raise | pending_only (partial) | `flush_failed:…` |
| S5 | P2 | decided: read-only | **done** | `done:` read-only SDP; contract output removed | fix-downstream (partial) | No compose SDP mint |
| S6 | P0 | decided: body writers only | **done** | `done:` `GAP_REPORT_BODY_WRITERS`={compose,layup}; sanitize/VO stamp fields only | dual SSOT / co-producer (partial) | Foreign full-body republish refused |
| S7 | P0 | unambiguous | **done** | `done:` drop persist `_cover_high_gaps_once`; HG-5 playbook seeds | responsibilities, fix-downstream | Persist never calls fill/seed |
| S8 | P1 | unambiguous | **done** | `done:` one `repair_gap_report` in compose persist | soft-heal | Single repair call |
| S9 | P1 | decided: peel floor under stamp+plan | **done** | `done:` hosted floor incompleteness ignored when stamp+plan live | responsibilities | Compose ignores floor under layup authority |
| S10 | P2 | needs_you | **open** | Sole post-land body writer (layup-only after stamp) **or** leave/monitor dual-era as federated | dual SSOT | Dual fail-if clears → PASS |

**Open cap:** S10 only. Safest shipped for S6/S9; dual-era remains the last hard fail-if.

**Operator decisions (2026-09-25):** S1–S5 shipped (S5=read-only SDP); S6–S9 shipped (S6=body writers only; S9=floor peel under stamp+plan).

---

## 7. Root-cause verdict

S1–S9 cut cover thrash, double repair, and stamp-era floor noise. One hard fail-if remains: intentional dual-era body SSOT (compose\|layup). Scorecard **FAIL** (`partial`). Next leverage is S10 decision — not more heal layers.

---

## 8. Recommended next action

`leave` (monitor) **or** decide S10 sole post-land writer.

Next: operator pick on **S10**; else leave dual-era federated and accept scorecard FAIL until product drops dual body writers.

---

## 9. Scope fence

Upstream poison owner (if any): `missing_framing` thin/sealed evals; G-Framing Yes without warrant clarity  
Downstream victims (names only): `nugget_layup_compose`, `gap_report_sanitize`, `full_master_ranking`, `vo_line_adjudicate` / `vo_synthesize`, `selection_framing_apply`, EDL VO seats  
Did **not** redesign other stages.
