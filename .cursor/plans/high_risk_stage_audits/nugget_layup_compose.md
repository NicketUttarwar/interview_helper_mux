# High-risk stage audit — nugget_layup_compose

tier: T0 | seed: #45 | runs_hit: 9/9  
status: `complete`  
mode: fix  
updated: 2026-09-25T17:05:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path: read live `master/selection.json` + `understanding/nugget_corpus.json` (plus soft topology / IP / gap / transcript context) → optionally prune on-air CTA scraps from selection → LLM-compose one layup row per ordered native (contentful before-VO **or** typed skip), sharding when the air order is long → in-memory heal/QC (spoken-copy, coverage materialize, high-salience recover/park, craft spine) → commit `understanding/nugget_layup_plan.json` → publish before-VO lines into `understanding/gap_report.json` under layup authority while preserving episode orientation and meeting the G-Framing Yes hosted VO floor → sync VO contract fingerprints.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `master/selection.json`, `understanding/nugget_corpus.json` | Contract hard inputs |
| Reads (soft) | `segments/manifest.json`, gap_report, mastering_plan, transcript, speakers, IP audit, ideal_cuts, … | Packet context only |
| Writes (SSOT) | `understanding/nugget_layup_plan.json` | Primary stage product |
| Co-writes | `understanding/gap_report.json` | Authoritative before-VO under `nugget_layup_authority` |
| Co-writes | `master/selection.json` | CTA omit / residue prune during compose (ALLOW) |
| Soft / side | `understanding/nugget_layup_qc.json`, masks, comprehension index, layup_candidates archive, omit_ledger, escalations | QC + thrash recovery |

### Rules that govern it

- **Admit** — selection sanitary + corpus present; hosted framing Yes implies synthetic VO seats exist or will be published
- **Refuse** — stale plan vs selection (`assert_layup_fresh_vs_selection`); hollow gap publish under G-Framing Yes floor; structural QC fail without viable aspirational candidate; `selection_commit_refused` on CTA prune
- **Incomplete** — `compose_shards_pending` / `compose_qc_pending`; `hosted_vo_floor_unsatisfiable` (operator / aspirational clear); `high_gap_unframed`; `layup_unsanitary`; selection unsanitary → resume sanitize
- **Heal** — CTA omit host-side; spoken-copy repair/skip; materialize over-skips; recover must-keep / high-salience; park on orientation; craft spine; framing-floor topup + rank-to-budget fill; pick-best candidate on oscillation
- **Wait_for_gate** — none owned here (G1 is optional after publish)
- **Done / hollow honesty** — refuse mark_done while shards/QC pending, floor unsatisfiable (unless aspirational proceed), or high-gap lacks interviewer line; freeze history once EDL sealed
- **Hard floors / QC bars** — `min_layup_coverage` (often aspirational advisory); `min_nugget_air_coverage` aspirational; catastrophic air coverage hard; craft (canned/thin/invented); hosted VO `need` from `min_synthetic_vo_lines` ∩ budget bands
- **Freeze / never_touch / ownership** — co-producer on gap_report + selection; DENY foreign flush; never-touch CTA skips; AuthorityDenied if compose tries to persist `segments/manifest.json` / foreign brief under freeze

### Considerations & load-bearing policy

- **G-Framing Yes** makes this stage the hosted-VO floor owner: empty/thin gap_report from upstream framing is not “fix by recompose forever” — floor topup / rank-to-budget / escalate.
- **Selection membership** is order_lock SSOT; layup must not invent order. CTA never-touch scraps must leave air before / during compose or transcript_excerpt needs thrash.
- **Dual product:** plan rows *and* gap_report lines must stay books-agree; publish is the choke point (`gap_report_write_lock`).
- **Full-auto** inherits production floors (no stub MusicGen; hosted VO real). Sparse-omit posture changes materialize vs valueless-skip path.

### LLM / external calls

- Prompt: `docs/prompts/nugget_layup/nugget-layup-compose.system.txt` (OF-03b / `llm_full`)
- ≤2 attempts per stage invoke (plus at most one degraded regenerate StageError inside persist)
- Shard batches when `len(ordered) > compose_batch_max_natives` (default 32)
- Hollow meaning refused: mid-shard empty plan, QC-pending stamp without publish, floor-unsatisfiable

### What it deliberately does *not* do

- Does not mint VO WAVs (`vo_synthesize`) or adjudicate delivery (`vo_line_adjudicate`)
- Does not write EDL / mix / transitions
- Does not own segment classification / manifest
- Does not invent framing evaluations (`missing_framing` / `gap_framing_compose` remain upstream for gap_eval + early lines)
- Does not re-rank primary air order (selection_order_sanitize / full_master_ranking)

### Operator-visible effects

- Escalation file `operator/escalations/nugget_layup_compose.json` on floor unsatisfiable
- Blocks refinement / selection_framing_apply / gap_report_sanitize / VO ladder until complete
- Every e2e failure brief in the 9-run corpus cites pre-EDL delivery QC incomplete pointing here

---

## 1. Job statement

Compose per-native before-VO layups from the nugget corpus onto the live selection air order, then publish those lines as the authoritative gap_report body so G1/VO/EDL have enough hosted synthetic seats and grounded bridges.

---

## 2. Error-hint intake

From the high-risk report. Classify each predicate.

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `hosted_vo_floor_unmet` | `still_present_on_HEAD` + partial `downstream_of_X` (gap_framing / selection thin) | Floor assert + incompleteness pin to this stage; often starved by upstream thin gap_report, but **publish/done honesty lives here** |
| `hosted_vo_floor_unsatisfiable` | `root_here` (policy surface) | Explicit escalate / aspirational proceed in `raise_hosted_vo_floor_unsatisfiable` + stage_completion |
| `selection_cta_omit` | `root_here` (host path) + `downstream_of_X` (ranking re-admit) | Host-executed omit in `llm_simple` + pre-compose prune; thrash when scraps re-enter via sanitize |
| `selection_commit_refused` | `still_present_on_HEAD` | Seen in exec_13198 forensics (4×); ownership/pending fights on selection write |
| `transcript_excerpt` | `still_present_on_HEAD` | LLM needs on garbled/CTA natives; demoted when CTA already omitted — still noisy (24× in 13198) |
| `layup_coverage` | `partial` / aspirational | Default aspirational advisory; structural hard only when aspirational off or catastrophic |
| `high_gap_unframed` | `still_present_on_HEAD` + `downstream_of_X` (gap_framing) | Layup listed in `_high_gap_unframed_incompleteness` so hollow done cannot land while high gap lack lines (5× in 13198) |
| `gap_report` unpaid / co-producer land | `root_here` (shared path) | Multi-ALLOW writers on gap_report; write lock + shared_path meta — unpaid land when pending/flush races |
| AuthorityDenied `segments/manifest.json` | `authority_friction` | Confirmed exec_13198: compose tried persist under pre_soft_freeze vs `segment_classification` |
| `layup_unsanitary` / shards pending | `still_present_on_HEAD` | Sanitize + NLC-B1 incompleteness; 10× unsanitary + shard stamp in 13198 |

Report why-high-risk: Hosted VO floor, CTA omit, selection thrash, gap_report unpaid land

Classification values: `root_here` | `downstream_of_X` | `seed_order_noise` | `authority_friction` | `still_present_on_HEAD` | `healed`

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `stages/analysis_extended.py::run_nugget_layup_compose` → `pipeline.py` dispatch |
| Key helpers | `nugget_layup.py` (~5.5k LOC): compose input, QC, publish, floor, candidates, skips, coverage |
| Host LLM / CTA | `llm_simple.py` (CTA omit + retry); `media_ip_cta.py` |
| Floor authority | `hosted_vo_authority.py`, `gap_fill_eligibility.py`, `floor_progress.py` |
| Done honesty | `stage_completion.py` (shards/QC/floor/high_gap/fresh/sanitary) |
| Sanitize | `artifact_sanitize/nugget_layup_plan.py` |
| Primary writes | `understanding/nugget_layup_plan.json`, `understanding/gap_report.json`, QC/candidates |
| Freeze / ownership | `artifact_ownership.py` ALLOW gap_report + selection + plan; DENY foreign gap flush |
| Contract | `docs/cross-cutting/stage-contracts/nugget_layup_compose.yaml` |
| Prompt | `docs/prompts/nugget_layup/nugget-layup-compose.system.txt` |
| Tests (non local-ML) | `test_nugget_layup.py`, `test_layup_compose_hardening.py`, `test_artifact_sanitize_layup.py`, `test_i6_layup_shard_pending.py`, `test_i7_stale_layup_floor_escalation.py`, `test_hosted_vo_*`, `test_rank_to_budget_vo.py`, `test_framing_floor_soft_omit_topup.py`, `test_media_ip_cta.py`, `test_layup_selection_commit_ownership.py`, … |

---

## 4. Business-logic walk

**Happy path** (`run_nugget_layup_compose`): CTA prune → `run_flow_llm_stage` (or proactive shards) → `persist` heals analysis/spoken-copy → QC → optional degraded regenerate (1×) → materialize / recover / park / spine / deterministic floor → on QC ok: write-lock → commit plan → `publish_layup_plan_to_gap_report` → assert authority + VO contract sync.

**Publish / floor** (`publish_layup_plan_to_gap_report`): build body from aired rows; keep orientation; suppress opening-owned duplicates; preserve operator/high_gap fills; if hosted Yes and active &lt; need → hollow-preserve prior, else framing-floor topup, else rank-to-budget fill, else `raise_hosted_vo_floor_unsatisfiable`.

**Incomplete:** mid-shard `_meta.compose_shards_pending` (unless final shard stamped with layups); `compose_qc_pending`; floor unsatisfiable (operator or aspirational clear); high_gap_unframed; freshness; layup_unsanitary; selection_unsanitary.

**Refuse:** loud QC fail; stale plan vs selection; selection_commit_refused; VO contract drift after rewrite.

**Heal loops (post S1–S5):** pre-LLM CTA prune only (no in-envelope omit+retry); persist still materialize → recover → park → spine → deterministic floor; publish floor-topup + rank-to-budget; oscillation pick-best disabled; candidates ≤2.

**LLM ≤2:** stage invoke cap; degraded regenerate is an extra StageError that consumes an attempt budget inside the same stage run.

**Done honesty:** incomplete reasons block hollow `.stage_done`; after EDL seal, layup incompleteness suppressed so mix is not rewound. S5: high_gap incompleteness on this stage only when plan claimed air for a still-missing high-gap line.

---

## 5. Over-engineering scorecard

### 5a — Baseline (pre S1–S5)

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **≥5** | Compose plan; CTA selection mutate; gap_report publish; hosted VO floor governance; QC/candidate archive; VO contract invalidate |
| Dual / competing SSOTs | **yes** | Plan rows vs gap_report interviewer_lines; both must agree under `nugget_layup_authority`; selection co-written for CTA |
| Soft-heal / thrash re-admit loops | **yes** | materialize ↔ recover ↔ park ↔ spine ↔ floor topup ↔ pick-best; CTA omit vs sanitizer restore; aspirational advisories |
| Co-producer / unpaid land | **yes** | gap_report ALLOW: missing_framing, gap_framing_compose, layup, selection_framing_apply, vo_line_adjudicate, sanitize, vo_synthesize; write lock + shared_path |
| Brittle predicates vs simple rules | **partial** | Many incompleteness tokens (shards, qc_pending, floor, high_gap, unsanitary) — necessary for honesty but high fan-out |
| Disproportionate shard/memo/resume | **yes** | Shard pending meta, candidate archive (12), attempt memos, escalations, air advisories |
| “Fix everything downstream” behavior | **yes** | Publish path tries to hold floor by restoring priors / rank-to-budget rather than failing fast to upstream framing |

**Over-engineered?** `yes`

### 5b — Re-score after S1–S5 (MODE=rescore 2026-09-25T16:50Z)

Hard fail-if (skill): responsibilities ≥3 · dual SSOT=yes · soft-heal=yes · co-producer unpaid=yes · brittle=yes · shard/memo=yes · fix-downstream=yes.  
`partial` on brittle / shard / fix-downstream does **not** trip fail-if.

| Check | Answer | Fail-if? | Evidence on HEAD |
|-------|--------|----------|------------------|
| Responsibilities count | **5** | **yes** (≥3) | (1) LLM compose plan (2) pre-LLM CTA selection mutate via `commit_layup_cta_selection` (3) gap publish + hosted floor in `commit_layup_gap_authority` → `publish_layup_plan_to_gap_report` (4) persist heal ladder: materialize/recover/park/spine/deterministic floor (5) VO contract sync after publish. S1 guarded mid-shard only — publish not peeled. `nugget_layup.py` ~5607 LOC / 121 defs |
| Dual / competing SSOTs | **yes** | **yes** | Plan rows vs gap_report `interviewer_lines` under `nugget_layup_authority`; selection still co-written for CTA |
| Soft-heal / thrash re-admit loops | **yes** | **yes** | S3 removed mid-LLM CTA omit+retry; S4 disabled oscillation pick-best. Persist heal chain + publish `_framing_floor_topup` / `apply_rank_to_budget_fill` still present |
| Co-producer / unpaid land | **yes** | **yes** | gap_report ALLOW multi-writer (`gap_framing_compose`, layup, `selection_framing_apply`, `vo_line_adjudicate`, sanitize, `vo_synthesize`) |
| Brittle predicates vs simple rules | **partial** | no | S5 claimed-air high_gap pin; shard/QC/floor/sanitary incompleteness remain |
| Disproportionate shard/memo/resume | **partial** | no | Candidates[-2:]; oscillation no-op. Shard pending + QC pending + escalations remain |
| “Fix everything downstream” behavior | **partial** | no | S5 framing owns high_gap by default. Publish still holds floor via topup / rank-to-budget |

**Fail-if hits:** 4 (responsibilities, dual SSOT, soft-heal, co-producer)  
**Over-engineered?** `yes`  
**Scorecard verdict: FAIL**

What would flip to PASS: ship open §6 rows S6–S9 (peel publish, drop CTA mutate, collapse heals, single gap land writer).

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | unambiguous | **done (partial)** | `done:` mid-shard gap-publish refuse via `commit_layup_gap_authority` / `_compose_shards_block_gap_publish` — **not** a separate stage | responsibilities / dual SSOT (partial) | Compose can QC plan without mid-shard gap stamp |
| S2 | P0 | unambiguous | **done** | `done:` layup `write_json` skips manifest/content_brief; hydrate uses `segment_classification` | authority friction (not a scorecard row) | Zero AuthorityDenied on those paths from this stage |
| S3 | P1 | unambiguous | **done** | `done:` removed in-envelope CTA omit+retry; demote needs only; pre-LLM prune retained | soft-heal (partial) | No selection mutate inside LLM incomplete loop |
| S4 | P1 | decided: simplify | **done** | `done:` candidates[-2:]; `try_pick_best_layup_on_oscillation` no-ops | shard/memo (partial) | Oscillation does not restore archive |
| S5 | P2 | decided: pin framing | **done** | `done:` `layup_claimed_air_missing_high_gap` + heal pin defaults framing | fix-downstream (partial) | Empty plan → `gap_framing_compose` |
| S6 | P0 | needs_you | **open** | **Peel** gap publish + hosted floor into thin `layup_gap_publish` seed (or compose plan-only; floor incompleteness only on publish stage) | responsibilities, dual SSOT | Compose `.stage_done` without write-locking gap; floor assert lives only on publish stage |
| S7 | P0 | unambiguous | **done** | `done:` removed pre-compose CTA selection mutate; layup dropped from `master/selection.json` producers; End-A CTA maps ranking/sanitize | responsibilities, soft-heal | Layup never writes `master/selection.json` |
| S8 | P1 | unambiguous | **done** | `done:` persist heal = single `ensure_deterministic_floor_before_refuse` then refuse (no materialize↔recover↔park↔spine ladder) | soft-heal, responsibilities | ≤1 heal helper call before `assert_layup_qc_or_raise` |
| S9 | P1 | decided: sole writer | **done** | `done:` gap_report producers = framing+layup only; stamp AllowRows; `assert_gap_report_body_sole_writer` post-authority text guard | co-producer unpaid land | Foreign full-body republish refused; unpaid land tests green |
| S10 | P2 | unambiguous | **done** | `done:` publish floor miss → `raise_hosted_vo_floor_unsatisfiable` only (no `_framing_floor_topup` / in-publish `apply_rank_to_budget_fill`; hollow preserve kept) | fix-downstream | No prior-line restore inside `publish_layup_plan_to_gap_report` |

**Open cap:** S6 (1). Prefer peel publish next `MODE=fix` after operator decide.

**Operator decisions (2026-09-25):** S4 simplify · S5 pin framing · S9 sole body writer · S1–S5 + S7–S10 shipped (S1 partial; S6 open).

---

## 7. Root-cause verdict

T0 choke narrowed: CTA mutate, heal ladder, multi-writer body land, and in-publish floor topup are shipped (S7–S10). Remaining overload is **publish+floor still inside compose** (S6 peel — needs_you). Scorecard may still FAIL on responsibilities/dual SSOT until S6.

---

## 8. Recommended next action

`simplify`

Next: **S6** peel gap publish / hosted floor into thin publish seed (operator decide), then `MODE=rescore`.

---

## 9. Scope fence

Upstream poison owner (if any): `gap_framing_compose` / `missing_framing` (thin or high_gap lines); `full_master_ranking` + `selection_order_sanitize` (CTA omit)  
Downstream victims (names only): `refinement_agenda`, `selection_framing_apply`, `gap_report_sanitize`, `vo_line_adjudicate`, `vo_synthesize`, `edl_narrative_audit`, `edl`, `sound_design_plan`  
Did **not** redesign other stages.
