# High-risk stage audit — master_finalize

tier: T2 | seed: #66 | runs_hit: 8/9  
status: `complete`  
mode: fix (safest S1–S5)  
updated: 2026-09-25T17:45:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

### What this stage does

Happy path: admit after mix + junction commitment → require G-listen + timeline-optimizer clear → **refuse** if optimizer best take unpaid (no nested remaster) → two-pass loudnorm `assembly.wav` → promote committed `master/master.wav` → authoritative listen_delight on master → evaluate thin structural PMQ (read-only seam autopsy) → persist PMQ + scorecard → stamp finalize only when delight + structural clear → mark G-Publish pending.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `master/assembly.wav`, `master/selection.json`, `master/junction_snip_qa.json`, `master/edl.json` | Contract hard inputs |
| Reads (soft) | seam autopsy (junction), render_ledger, transitions, omit_ledger, gap_report, SDP, mastering_plan, hitch | Soft / read-only |
| Writes (SSOT) | `master/master.wav`, `master/post_master_quality.json`, `master/listener_scorecard.json`, `master/failure_review.json` | Finalize own |
| Co-writes | `mastering/listen_delight_audit.json` (w/ `listen_delight_audit`) | Ship-time delight rewrite only |
| Soft / side | `run_meta.json` qc_summaries, ship-gate meta key, G-Publish pending | Ops / hollow honesty |

### Rules that govern it

- **Admit** — assembly present + integrity; EDL seat preflight; G-listen clear; timeline optimizer clear / already applied
- **Refuse** — unpaid optimizer best; empty/corrupt assembly; pre_master blocking; truncated master; delight floors fail; structural PMQ fail
- **Incomplete** — missing/truncated master, malformed PMQ, or ship-gate-open after delight/structural fail
- **Heal** — early promote of staged master only (no omit/VO/junction heals)
- **Wait_for_gate** — `require_g_listen_clear`; land-honest wait clear
- **Done / hollow honesty** — stamp only after PMQ+delight; unmark on ship-fail; persist PMQ even if delight throws
- **Hard floors** — thin structural: exists, seam commitment, duration, spoken VO, audible hash, omit contract; live critical junction residuals still hard
- **Freeze / ownership** — primary master.wav + PMQ; delight co-ALLOW; autopsy SSOT is junction only

### Considerations & load-bearing policy

- Authoritative listen delight ship gate lives here (pre-mix pass non-blocking).
- Full-auto = no soft music/junction PMQ waive.
- Rubric/advisory PMQ checks remain visible under aspirational but do not hard-block.

### LLM / external calls

- Indirect: listen_delight evaluation; ffmpeg loudnorm (local).

### What it deliberately does *not* do

- Nested `take_best` / `run_junction_snip_qa`
- Rewrite seam autopsy
- Entry-book omit/VO heals
- Re-score delight floors inside PMQ

### Operator-visible effects

- Blocks G-Publish / encode until PMQ `publish_allowed` + delight clear
- Loud `optimizer_best_unpaid` pins remaster upstream

---

## 1. Job statement

Promote mix assembly to a loudness-legal `master/master.wav` and refuse ship unless thin structural PMQ and authoritative listen delight clear — with honest done stamps only after that envelope lands.

---

## 2. Error-hint intake

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| LoudStageFailure `post_master_quality_failed` | `still_present_on_HEAD` + often `downstream_of_junction_snip_qa` | Thin structural / critical residuals |
| Hollow `mark_done` | `healed` (persist-then-unmark) | Ship-gate-open still hollow until clear |
| `optimizer_best_unpaid` | `root_here` (new refuse) | Replaces nested remaster |
| `listen_delight_floors_failed` | `root_here` (gate host) | Sole delight judge at ship |
| Soft / e2e junction soften | `healed` for production path | Full-auto refuses soft music/junction |

Report why-high-risk: post_master_quality / hollow mark_done

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `stages/mastering.py::run_master_finalize` |
| Loudnorm export | `master_wav`, `_master_filter_chain`, `_ffmpeg_loudnorm_probe` |
| Ship gate body | `post_master_quality.py::run_post_master_quality` / `evaluate_post_master_quality` |
| Delight at ship | `listen_delight.py::run_authoritative_listen_delight_at_ship` |
| Done honesty | `done_authority.py` — `finalize_*`, `stamp_finalize_on_success`, `unmark_finalize_after_ship_fail` |
| Structural set | `aspirational_quality.STRUCTURAL_PMQ_CHECKS` (thin S5) |
| Freeze / ownership | master.wav, PMQ, scorecard; delight co-ALLOW; autopsy = junction only |
| Contract | `docs/cross-cutting/stage-contracts/master_finalize.yaml` |
| Tests | `test_finalize_s1_s5_simplify.py`, `test_post_master_quality.py`, `test_done_authority.py`, `test_i11_pmq_persists_when_delight_fails.py`, … |

---

## 4. Business-logic walk

1. **Happy** — gates clear → optimizer already seated → loudnorm + promote → delight pass → structural PMQ pass → stamp → G-Publish pending.
2. **Incomplete** — master/PMQ hollow or ship-gate-open.
3. **Refuse** — unpaid optimizer; integrity; delight loud-fail; structural PMQ.
4. **Heal** — staged master promote only.
5. **LLM ≤2** — N/A as stage invoke.
6. **Done honesty** — SHIP-HOLLOW-FINALIZE preserved.

---

## 5. Over-engineering scorecard

### 5a — Baseline (investigate)

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **5** | heal · optimizer+junction · loudnorm · PMQ kitchen · delight+stamp |
| Dual / competing SSOTs | **yes** | delight + autopsy co-owned; PMQ re-scored delight |
| Soft-heal / thrash re-admit loops | **yes** | nested remaster; unmark re-admit |
| Co-producer / unpaid land | **yes** | autopsy + book heals + nested junction |
| Brittle predicates vs simple rules | **yes** | structural/rubric/aspirational/soft matrices |
| Disproportionate shard/memo/resume | **no** | |
| “Fix everything downstream” behavior | **yes** | nested junction + sweeps |

**Over-engineered?** `yes`  
**Scorecard verdict:** `FAIL`

### 5b — Re-score after changes (MODE=fix)

| Check | Answer | Delta | Evidence now |
|-------|--------|-------|--------------|
| Responsibilities count | **2** | −3 | (1) gates + loudnorm/promote (2) delight ship judge + thin PMQ + honest stamp |
| Dual / competing SSOTs | **no** | ↓ S2/S3 | PMQ delight floors deleted; autopsy write dropped; one ship delight judge |
| Soft-heal / thrash re-admit loops | **partial** | ↓ S1 | Nested remaster gone; unmark-after-ship-fail remains honest |
| Co-producer / unpaid land | **partial** | ↓ S3/S4 | Delight co-write kept (intentional); autopsy/book heals gone |
| Brittle predicates vs simple rules | **no** | ↓ S5 | Thin STRUCTURAL set; demoted checks are rubric |
| Disproportionate shard/memo/resume | **no** | same | |
| “Fix everything downstream” behavior | **no** | ↓ S1 | Refuse unpaid optimizer upstream |

**Over-engineered?** `no` — responsibilities ≤2; no hard fail-if `yes` rows (partials are load-bearing honesty).

**Scorecard verdict:** `PASS`

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | needs_you | **done** | `done:` refuse unpaid optimizer (`optimizer_best_unpaid`); no `take_best` / nested junction | Responsibilities + fix-downstream | `test_finalize_s1_s5_simplify.py::test_s1_*` |
| S2 | P0 | needs_you | **done** | `done:` deleted PMQ `listen_delight_floors` re-score; delight alone judges | Dual SSOT | `test_s2_*` + `test_post_master_quality.py` |
| S3 | P0 | needs_you | **done** | `done:` PMQ read-only autopsy; ALLOW/contract drop finalize as autopsy writer | Co-producer | `test_s3_*`; ownership row junction-only |
| S4 | P1 | unambiguous | **done** | `done:` removed omit heal / VO sync / layup ensure from finalize entry | Co-producer + responsibilities | `test_s4_*` |
| S5 | P1 | needs_you | **done** | `done:` thin STRUCTURAL ship bar; demoted music/opening/defect/reachability to rubric | Brittle predicates | `test_s5_*`; aspirational_quality sets |

Status: `done` · Operator decisions (2026-09-25): **safest S1–S5**.

Backlog (parked): `require_publishable` live autopsy re-eval greenwash; peel delight co-write if listen_delight stage owns post_master rewrite.

---

## 7. Root-cause verdict

Kitchen peeled. Finalize is loudnorm + thin structural gate + authoritative delight stamp. Corpus residual Loud fails should pin unpaid upstream (junction/mix/optimizer/delight), not a nested remaster kitchen inside finalize.

---

## 8. Recommended next action

`leave` — monitor unpaid-optimizer refuse + thin PMQ in full-auto; optional backlog on publish-path autopsy refresh.

---

## 9. Scope fence

Upstream poison owner (if any): `junction_snip_qa`, `mix`, optimizer take-best owner, `listen_delight_audit`  
Downstream victims (names only): `master_transcript_build`, `podcast_encode_mp3`, `podcast_publish`  
Did **not** redesign other stages.
