# High-risk stage audit — mix

tier: T2 | seed: #64 | runs_hit: 8/9  
status: `complete`  
mode: fix  
updated: 2026-09-25T17:45:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

### What this stage does

Happy path: assert spend + consumer air-order → refuse if live incomplete-cut criticals remain → publishability `pre_mix` → rebind episode-close cue (no invent) + theme bookends → ensure MMAudio QA → **refuse** missing transition pairs → `sound_design.mix()` builds speech+VO base timeline from live EDL + ingest, applies SDP overlays, writes `master/assembly.wav` + coverage/QC → post-mix QC **assert** (no remux re-admit) → promote assembly → `_seat_after_mix` (clear remaster / speech-first stamp).

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `ingest/normalized.wav`, `master/selection.json`, `master/edl.json`, `understanding/sound_design_plan.json` | Contract hard inputs |
| Reads (soft) | transitions, junction_snip_qa, seam_autopsy, omit_ledger, gap_report, mmaudio_qa | Gates / overlays / refuse |
| Writes (SSOT) | `master/assembly.wav`, `master/music_cue_coverage.json` | Primary product of mix |
| Co-writes | live `master/edl.json` (**realized times only**), `master/air_order.json`, `master/render_ledger.json`, bed QC / listen_critic | Delivery seating bus + QC |
| Soft / side | `mix_junction_seat` epoch | HAU seat — no post-mix delight write |

### Rules that govern it

- **Admit** — EDL + selection + SDP present; music-listen requirement; theme bookends ready; speech-first may defer beds until remaster
- **Refuse** — live incomplete-cut criticals; publishability `pre_mix`; missing transition/VO WAV → LoudFail pin `vo_synthesize`; missing/shortened music when beds not deferred; intel/bed fail / soundscape fail_closed
- **Incomplete** — `_mix_unseated_incompleteness` until `mix_outputs_seated` + remaster land paid
- **Heal** — none in-body (S3/S4 peeled remux + last-chance); nested junction remaster still calls `mix()` with inner incomplete-cut skip
- **Wait_for_gate** — incomplete cuts pin junction; music-epoch beds after seated (HAU)
- **Done / hollow honesty** — demote hollow `.stage_done/mix` when unseated / remaster unpaid
- **Hard floors** — incomplete-cut refuse; no inventing outro; missing VO refuse
- **Freeze / ownership** — ALLOW assembly + coverage + QC; DENY mix→vo_pickup; delight owned by finalize/listen_delight only

### Considerations & load-bearing policy

- Selection leads order; seating fails if lock ≠ EDL speech ids.
- Mix↔junction seat is the federal resume pin.
- Speech-first HAU: first seat may omit beds; remaster owed via `note_speech_first_mix` at boundary only.

### LLM / external calls

N/A for core render.

### What it deliberately does *not* do

- Own junction incomplete-cut repair
- Own listen-delight ship gate (or rewrite delight audit)
- Listenability craft rewrite of live EDL
- Last-chance VO / transition synth

### Operator-visible effects

- Blocks while junction criticals live or VO/transition WAVs missing
- Assembly.wav feeds finalize / delight

---

## 1. Job statement

Render a seated `master/assembly.wav` from the live EDL + SDP overlays, refuse when junction left hanging mid-thought cuts or required WAVs are missing, and mark mix seed-complete only when assembly is committed to the live air-order generation.

---

## 2. Error-hint intake

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `incomplete_cut_unresolved` | `downstream_of_junction_snip_qa` / `still_present_on_HEAD` | Mix correctly refuses; heal playbook pins junction. |
| `mix_seat` / unseated / hollow done | `root_here` / `still_present_on_HEAD` | HAU seating kept; demote hollow done load-bearing. |
| AuthorityDenied vs `listen_delight_audit` | `healed` | S1 deleted post-mix delight rewrite |
| seed-order (layup / delight incomplete) | `seed_order_noise` | Homunculus noise |
| `selection_edl_order_drift` | `downstream_of_edl` | Seating fails closed |
| delight freeze / remutate under seal | `authority_friction` | Ship gate `#60` / finalize |

Report why-high-risk: incomplete_cut_unresolved, mix_seat, delight freeze

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `stages/assembly.py::run_mix` + `_seat_after_mix` |
| Core render | `sound_design.mix` |
| Overlays | `build_flow1_overlays` / `flow1_overlays_from_sdp` |
| Incomplete-cut refuse | `junction_snip_qa.refuse_mix_if_live_incomplete_cuts` |
| Publishability | `publishability_boundary.checkpoint_publishability(pre_mix)` |
| Seating SSOT | `air_order.mix_outputs_seated`; `mix_junction_seat.*` via `_seat_after_mix` |
| Done honesty | `stage_completion._mix_unseated_incompleteness`; `demote_hollow_mix_done` |
| Freeze / ownership | ALLOW assembly + coverage + QC; DENY mix→vo_pickup |
| Tests | `test_mix_s1_s5_simplify.py` + seat/HX suite |

---

## 4. Business-logic walk

1. **Happy** — preflight clean → render → QC assert → promote → `_seat_after_mix` → done when seated+paid.
2. **Incomplete** — unseated / remaster unpaid.
3. **Refuse** — incomplete cuts; missing transition/VO WAV; music missing (non-deferred); QC fail_closed / intel remux_on_fail.
4. **Heal** — peeled (S3/S4); junction may nested-remaster via same `mix()`.
5. **LLM ≤2** — N/A.
6. **Done honesty** — seated + remaster paid.

---

## 5. Over-engineering scorecard

### 5a — Baseline (investigate)

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **5** | (1) preflight gates (2) speech+VO+overlay render (3) multi-axis remux QC (4) live EDL / air_order / ledger co-writes (5) seat/remaster bookkeeping + post-mix delight rewrite |
| Dual / competing SSOTs | **yes** | Seating facades + delight mix rewrite vs finalize/delight ALLOW |
| Soft-heal / thrash re-admit loops | **yes** | Remux recursion; last-chance VO; remaster stamp thrash |
| Co-producer / unpaid land | **yes** | Listenability + delight foreign writes |
| Brittle predicates vs simple rules | **partial** | Seating stack named but heavy |
| Disproportionate shard/memo/resume | **partial** | Remux meta + QC JSONs |
| “Fix everything downstream” behavior | **yes** | Last-chance VO, listenability EDL, delight re-score |

**Over-engineered?** `yes`  
**Scorecard verdict:** `FAIL`

### 5b — Re-score after changes (MODE=fix)

| Check | Answer | Delta | Evidence now |
|-------|--------|-------|--------------|
| Responsibilities count | **2** | −3 | (1) refuse unclean + render/QC assert (2) `_seat_after_mix` boundary |
| Dual / competing SSOTs | **no** | ↓ S1 | No mix→delight write; HAU seat remains sole seating module |
| Soft-heal / thrash re-admit loops | **no** | ↓ S3/S4 | No recursive remux; no last-chance synth; no listenability heal |
| Co-producer / unpaid land | **partial** | ↓ S2 | Realized-time `write_live_edl` kept (safest S2); listenability peeled |
| Brittle predicates vs simple rules | **partial** | same | Seating stack unchanged (intentional HAU) |
| Disproportionate shard/memo/resume | **no** | ↓ S3 | Remux meta mutate removed |
| “Fix everything downstream” behavior | **partial** | ↓ S1/S4 | Episode-close rebind only residual |

**Over-engineered?** `no` — responsibilities ≤2; no hard fail-if `yes` rows (residuals are partial only).

**Scorecard verdict:** `PASS`

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | needs_you | **done** | `done:` deleted `rerun_listen_delight_after_mix` from `run_mix` | Dual SSOT + co-producer | `test_mix_s1_s5_simplify.py::test_s1_*` |
| S2 | P0 | needs_you | **done** | `done:` peeled listenability remediate + `mix_listenability` write; kept `mix_realized_times` | Co-producer | `test_s2_*` |
| S3 | P0 | unambiguous | **done** | `done:` no recursive `return mix(...+1)`; bed QC advisory-only (no meta mutate) | Soft-heal thrash | `test_s3_*` |
| S4 | P1 | needs_you | **done** | `done:` LoudFail missing pairs/VO; no commit/restamp/last-chance; `missing_vo_retry_once=false` | Fix-downstream | `test_s4_*` |
| S5 | P1 | needs_you | **done** | `done:` `_seat_after_mix` helper; run_mix ≈ refuse → render → seat | Responsibilities | `test_s5_*` |

Status: `open` | `done` | `superseded` · Operator decisions (2026-09-25): **all safest** — S1 delete delight; S2 peel listenability keep realized; S3 no remux; S4 refuse VO; S5 keep HAU thin body.

Open rows: none (PASS). Optional backlog: peel `mix_realized_times` if ledger alone can seat; peel episode_close rebind upstream.

---

## 7. Root-cause verdict

S1–S5 landed. Mix is refuse unclean → one render → seat assert. Residual partials (realized-time EDL stamp, episode_close rebind, seating predicate weight) are load-bearing HAU, not dual SSOTs. Upstream incomplete cuts remain the true product refuse path.

---

## 8. Recommended next action

`leave` — scorecard **PASS** after S1–S5. Do not add heal layers.

---

## 9. Scope fence

Upstream poison owner (if any): `junction_snip_qa`, `vo_synthesize` / `transitions`, music epoch  
Downstream victims (names only): `master_finalize`, `listen_delight_audit`, `podcast_publish`  
Did **not** redesign other stages.
