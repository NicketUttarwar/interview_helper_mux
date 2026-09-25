# High-risk stage audit — gap_report_sanitize

tier: T1 | seed: #46 | runs_hit: 2/9 (severe when present)  
status: `complete`  
mode: rescore  
updated: 2026-09-25T18:16:47Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path: after `nugget_layup_compose` has published VO into `understanding/gap_report.json`, this stage reads that JSON → runs deterministic `sanitize_gap_report` (shape → drop incomplete omit stubs → dedupe → rebase/drop off-air → at-most-one orientation → omit optional scaffolding → refuse residual scaffolding → sanitize stamp) → writes sanitize audit → persists via `file_store.write_json` with S1 land stamp (preserve paid co-producer) → `heal_or_raise`.

If the file is missing: framing Yes → refuse (S4, no stub); framing No → empty sanitary stub may complete.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (soft) | `understanding/gap_report.json` | Soft input; contract names `gap_framing_compose` but live body author is usually `nugget_layup_compose` post-authority |
| Reads (soft) | `master/selection.json` | Order lock + off-air drop / rebase |
| Writes (SSOT claim) | `understanding/gap_report.json` | Shared primary — sanitize is stamp/shape co-writer, not sole body author |
| Soft / side | sanitize audit under operator / artifact_sanitize | Actions + metrics |
| Shared bus | `commit_gap_report_doc` | Preferred persist path for repair modules; also cascades spoken-text → VO |

### Rules that govern it

- **Admit** — gap present (or framing-No empty stub) + `result.ok` after sanitize
- **Refuse** — `sanitize_refused:gap_report:` (`scaffolding_active:…`, shape invalid)
- **Incomplete** — `gap still unsanitary` → resume here; framing Yes + missing gap → resume `nugget_layup_compose` (S4); high_gap_unframed; compose-thin coverage → layup (S3)
- **Heal** — bounded shape only: drop incomplete omit stubs, dedupe, drop off-air, omit optional scaffolding; **no** required body rewrite (S2); **does not** seat/clamp (air_contract W3)
- **Wait_for_gate** — none (G-Framing / G1 are upstream)
- **Done / hollow honesty** — HR-4: refuse mark when unsanitary; S1 preserves paid co-producer `producer_stage`; unpaid only when missing/foreign
- **Hard floors / QC bars** — orientation drop gated by `hosted_vo_authority`; coverage floor owned by layup honesty (`gap_layup_coverage_errors`)
- **Freeze / never_touch / ownership** — ALLOW stamp fields; S9 body writers = framing + layup; S5 stamp-only commit bus asserts sole body writer

### Considerations & load-bearing policy

- **Report heat is mostly seed-order:** when layup/fuse/ranking stall, this stage piles recoveries even when it is not the root (report cluster with `#45` / `#47` / `#49`).
- **Shared-path land (S1):** stamp/sanitize claims preserve layup/framing/recompose `producer_stage`; claim sanitize only when unpaid/foreign.
- **W1 vs W3:** shape/dedupe/rebase/optional-omit/lock only; seat clamp + omit-ledger sync live in air_contract.
- **Publishability / Full-auto:** no human gate; honest stall on refuse / missing framing gap.

### LLM / external calls

N/A — deterministic process stage. Contract YAML still lists `llm_execute` in lifecycle phases (doc drift vs body).

### What it deliberately does *not* do

- Does not compose gap body or mint layup plan (framing / layup)
- Does not own VO seats / omit_ledger clamp (air_contract)
- Does not write selection / EDL / mix
- Does not rewrite required scaffolding text (refuse upstream)
- Does not own compose-thin coverage refuse (layup)

### Operator-visible effects

- Sanitize refuse / unsanitary → incompleteness pin (resume sanitize or layup)
- Framing Yes + missing gap → “resume nugget_layup_compose” (no stub file)
- Content hash change invalidates VO/EDL cascade markers
- No GUI gate

---

## 1. Job statement

Deterministically clean and stamp `understanding/gap_report.json` so downstream VO/EDL never build on duplicate, off-air, or scaffold-dirty gap lines — without claiming seat/omit authority or body authorship.

---

## 2. Error-hint intake

From the high-risk report. Classify each predicate.

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| Seed-order pile-up waiting on `#45 nugget_layup_compose` / hitch / fuse / ranking | `seed_order_noise` | Unchanged — recoveries spam when layup unpaid/incomplete |
| Gap ownership / shared-path co-producer land | `healed` | S1 preserve + co-producer allowlist; unpaid only when missing/foreign (`test_grs_s1_s5` / unpaid matrix) |
| `gap still unsanitary` / `scaffolding_active` | `still_present_on_HEAD` | Honest refuse; S2 no rewrite soft-heal |
| `layup_coverage_below_floor` | `healed` (moved) | S3: `gap_layup_coverage_errors` + layup incompleteness / pin |
| Empty stub / hollow done while framing Yes | `healed` | S4: no stub seed; missing → pin layup |
| `authority_undo_thrash` on gap_report commit bus | `authority_friction` | Bus remains; S5 blocks stamp-only body mutates |

Report why-high-risk: Seed-order + gap ownership co-producer land

Classification values: `root_here` | `downstream_of_X` | `seed_order_noise` | `authority_friction` | `still_present_on_HEAD` | `healed`

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `artifact_sanitize/gap_report.py::run_gap_report_sanitize` |
| Core sanitize | `sanitize_gap_report` (same file) — steps 1–7 |
| Shared commit bus | `commit_gap_report_doc` → `_persist_gap_disk` + `_cascade_gap_spoken` |
| Sanitary gate | `gap_sanitary_errors` / `gap_doc_sanitary_errors` |
| Done honesty | `stage_completion` (`gap_report_sanitize` branch, GRS-B2 empty stub, high_gap_unframed) + `heal_or_raise` |
| Land honesty | `done_authority.SHARED_PATH_PRODUCER_STAGES` + `_SHARED_PATH_LAND_CO_PRODUCERS` |
| Freeze / ownership | `artifact_ownership` ALLOW stamp fields; `GAP_REPORT_BODY_WRITERS` / `assert_gap_report_body_sole_writer` (write_json path — **bypassed** by `fs_write_json` here) |
| Contract | `docs/cross-cutting/stage-contracts/gap_report_sanitize.yaml` |
| Forbidden W3 mutates | `artifact_sanitize/precedence.py::GAP_SANITIZE_FORBIDDEN_MUTATIONS` |
| Tests (non local-ML) | `test_grs_s1_s5_simplify.py`, `test_artifact_sanitize_gap.py`, `test_hollow_seed_sanitary.py`, `test_r2_scaffold_sanitize.py`, `test_unpaid_land_matrix.py`, `test_sanitize_authority_thrash.py` |

---

## 4. Business-logic walk

**Happy path** (`run_gap_report_sanitize`): reentry guard → load gap (or framing-No empty stub) → `sanitize_gap_report` → audit → S1 land stamp → `fs_write_json` → optional invalidate → `heal_or_raise`.

**Sanitize steps** (`sanitize_gap_report`): sanitary hash early exit → shape → drop incomplete omit stubs → dedupe → rebase/drop off-air → at-most-one orientation → omit optional scaffolding (S2: no required rewrite) → refuse residual scaffolding → stamp meta. Coverage floor is **not** here (S3 → layup).

**Incomplete:** unsanitary residuals; framing Yes + missing gap → pin layup (S4); high_gap_unframed; shared-path unpaid when producer missing/foreign (co-producers paid; S1 preserves claim).

**Refuse:** shape invalid; `scaffolding_active` on required lines. Coverage → layup incompleteness.

**Heal:** drop stubs/off-air/dupes; omit optional scaffolding; `commit_gap_report_doc` may persist unsanitary with `ok=False` (availability). S5: stamp-only commits refuse body text mutates.

**LLM ≤2:** N/A.

**Done honesty:** S4 missing+framing Yes pins layup; sanitary errors block mark_done; unpaid shared-path blocks promote until stamp/co-producer clears.

---

## 5. Over-engineering scorecard

### 5a — Baseline (pre S1–S5)

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **4** | (1) shape/dedupe/rebase/opening clean (2) scaffolding soft-heal + refuse (3) layup coverage floor gate (4) shared commit bus + spoken cascade + empty-stub seed + producer land stamp |
| Dual / competing SSOTs | **yes** | S9 says framing/layup sole body text writers; sanitize rewrote `text`/`script` and always claimed `producer_stage` |
| Soft-heal / thrash re-admit loops | **yes** | Scaffolding rewrite; `persisted_unsanitary`; empty stub under framing Yes |
| Co-producer / unpaid land | **yes** | Forced `producer_stage=gap_report_sanitize` every run |
| Brittle predicates vs simple rules | **partial** | compose_thin + coverage + scaffolding codes |
| Disproportionate shard/memo/resume | **no** | |
| “Fix everything downstream” behavior | **partial** | Spoken cascade + soft-heal copy |

**Over-engineered?** `yes`  
**Scorecard verdict:** `FAIL` (baseline)

What would flip FAIL → PASS: peel to ≤2 responsibilities; stop body rewrite; preserve co-producer land; move coverage to layup.

### 5b — Re-score after changes (MODE=rescore 2026-09-25T18:16:47Z)

Hard fail-if (skill): responsibilities ≥3 · dual SSOT=yes · soft-heal=yes · co-producer unpaid=yes · brittle=yes · shard/memo=yes · fix-downstream=yes.  
`partial` does **not** trip fail-if.

HEAD verified: `_resolve_gap_land_producer` / `_strip_scaffolding` (no rewrite) / `gap_layup_coverage_errors` + stage_completion pin / framing-Yes missing refuse / `_assert_stamp_stage_no_body_text` on commit. Pins: **25 passed** (`test_grs_s1_s5_simplify` + gap sanitize + hollow seed + unpaid land gap cases).

| Check | Answer | Fail-if? | Evidence now |
|-------|--------|----------|--------------|
| Responsibilities count | **2** | no | (1) shape/dedupe/rebase/opening + optional-omit + refuse + land stamp (2) shared commit bus with S5 body guard. Coverage on layup (S3); empty stub framing-No only (S4) |
| Dual / competing SSOTs | **no** | no | No body rewrite; stamp-only commits assert sole body writer |
| Soft-heal / thrash re-admit loops | **partial** | no | Optional omit + `persisted_unsanitary` remain; rewrite + hollow framing stub gone |
| Co-producer / unpaid land | **partial** | no | Still ALLOW stamp co-writer; S1 does not thrash-claim over layup/framing |
| Brittle predicates vs simple rules | **partial** | no | Scaffolding codes + hosted_vo orientation gate |
| Disproportionate shard/memo/resume | **no** | no | Sanitary hash + reentry only |
| “Fix everything downstream” behavior | **partial** | no | Spoken cascade remains; body soft-heal peeled |

**Fail-if hits:** 0  
**Over-engineered?** `no`  
**Scorecard verdict:** `PASS`

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | unambiguous | done | Preserve `_meta.producer_stage` for paid co-producers on stamp/sanitize claims (`_resolve_gap_land_producer`) | Co-producer thrash | HEAD + `test_grs_s1_s5_simplify::test_s1_*` |
| S2 | P0 | unambiguous | done | Required scaffolding: no rewrite — refuse `scaffolding_active`; optional omit only | Dual SSOT + soft-heal | HEAD `_strip_scaffolding`; `test_r2_scaffold_sanitize` |
| S3 | P1 | needs_you→safest | done | Drop coverage from sanitize; `gap_layup_coverage_errors` + layup incompleteness + pin table | Responsibilities | HEAD stage_completion + `test_grs_s1_s5_simplify::test_s3_*` |
| S4 | P1 | unambiguous | done | Framing Yes + missing: raise, no empty stub; incompleteness pins layup | Soft-heal hollow seed | HEAD `run_gap_report_sanitize`; hollow-seed tests |
| S5 | P2 | needs_you→safest | done | Stamp-only stages on `commit_gap_report_doc` must pass `assert_gap_report_body_sole_writer` | Dual SSOT / fix-downstream | HEAD `_assert_stamp_stage_no_body_text`; `test_s5_*` |

Operator decisions: build S1–S5 with safest options (2026-09-25). Rescore confirms all five still on HEAD.

Open rows: none — leave / monitor spoken cascade + `persisted_unsanitary` only if thrash returns.

---

## 7. Root-cause verdict

Ledger heat remains mostly seed-order on layup. Stage over-build (body rewrite, always-claim land, coverage gate, hollow stub) peeled via S1–S5; sanitize is shape+stamp with guarded commit bus.

---

## 8. Recommended next action

`leave` — scorecard PASS after S1–S5; monitor only.

---

## 9. Scope fence

Upstream poison owner (if any): `nugget_layup_compose` (hollow/unpaid publish), `connector_fuse_pass_pre_ranking` / ranking seed-order backlog  
Downstream victims (names only): `refinement_agenda`, `vo_line_adjudicate`, `vo_synthesize`, `edl`, `edl_narrative_audit`, `assembly_preview`  
Did **not** redesign other stages.
