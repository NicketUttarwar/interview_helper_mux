# High-risk stage audit — vo_synthesize

tier: T1 | seed: #55 | runs_hit: 8/9  
status: `complete`  
mode: fix  
updated: 2026-09-25T17:26:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path: VO ladder ready (adjudicate + G1 synth path) → optional Full-auto rewrite of residual `delivery:record` → synth → stamp omit-ledger skips onto `gap_report` → synthesize current-pair transition WAVs → resync missing/stale gap synthesize WAVs → promote pending stems → heal seated bind mismatches → restamp EDL `source_path`s for transitions/VO → persist `mastering/vo_synthesize.json` → `assert_seated_vo_rendered` → stamp hard seat freeze.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `understanding/gap_report.json`, `master/transitions.json` | Contract + clinic B2 |
| Reads (soft) | mastering plan / air seats, omit ledger, voice ref / clone consent, G1 state | Implicit deps understated in YAML soft: [] |
| Writes (SSOT) | `mastering/vo_synthesize.json`, `vo_pickup/**`, `master/transitions/*.wav` | Primary product = WAVs; JSON is status/pair gap |
| Soft / side | `vo_pickup/synthesis_report.json`, timbre/clone audits; stamps on `gap_report` delivery/omit; may mutate `mastering_plan` seats on bind-fail omit; may restamp `master/edl.json` source paths | ALLOW stamp fields; EDL restamp is co-write |

### Rules that govern it

- **Admit** — `require_vo_path_ready(for_synthesize=True)`; Full-auto may auto-accept gate defaults; Chatterbox + voice_ref for record→synth rewrite
- **Refuse** — SystemExit when ladder incomplete / no synthesize lines; hard seat freeze stamp failure raises (not soft-pass)
- **Incomplete** — missing/stale seated WAVs, G1 holes, missing transition pairs, gap/air/vo unsanitary, hollow seats; `vo_synthesize_should_defer_done` keeps `.stage_done` off
- **Heal** — `heal_seated_bind_mismatch`: promote → accept on-disk WAV → resynth → omit last (non-orientation); fail-open flush continues walk toward mix last-chance
- **Wait_for_gate** — **G1** (record path needs operator outside Full-auto); G8 stability waits layup/transitions
- **Done / hollow honesty** — B1 KEEP: done-without-wav forbidden; reconcile clears hollow markers; seated assert fail-closed at end of run
- **Hard floors / QC bars** — seated synthesize lines must have WAV/bind; current transition pairs; hard seat freeze after success
- **Freeze / never_touch / ownership** — owner of `vo_pickup` + status JSON; ALLOW field stamps on gap delivery/omit; nested synth under EDL lease still writes pending under `vo_synthesize` tree

### Considerations & load-bearing policy

- **G1** is the human/automation seam; Full-auto owns residual record lines via synth rewrite (clinic B3) once voice reference approved.
- **Hosted VO / selection seats** decide which lines must render; this stage does not invent copy.
- Missing WAVs here are the dominant poison into `edl_narrative_audit` (`edl_narrative:vo_g1`) and `edl`.
- Publishability: never soft-done without audible stems; mix may last-chance synth once, but seed-complete honesty stays here.

### LLM / external calls

No OpenAI. Local Chatterbox / S2S via `s2s_runner.synthesize_line` / `synthesize_spoken_transitions`. Model quality N/A for this audit — host honesty only.

### What it deliberately does *not* do

- Does not adjudicate final spoken text (`vo_line_adjudicate`)
- Does not compose framing / layup copy
- Does not build `master/edl.json` structure (only optional source_path restamp)
- Does not own G-Framing decision (upstream)

### Operator-visible effects

- G1 gate in GUI when record delivery remains; Full-auto rewrites to synth when clone path ready
- Incomplete stage blocks narrative audit / EDL until WAVs land
- Fail-open after flush can advance walk while stage stays incomplete (operator still sees holes)

---

## 1. Job statement

Render and bind every seated synthesize + current-pair transition WAV the air order needs, then refuse done until those stems (and hard seat freeze) are honest — without inventing VO copy.

---

## 2. Error-hint intake

From the high-risk report. Classify each predicate.

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `seed_order` / must complete `vo_line_adjudicate` | `seed_order_noise` | Dominant forensics (335× `seed_order_prereq`); MUST_PRECEDE, not craft bug |
| `vo_g1` / `handle_gate` / `delivery:premature_complete:vo_g1` | `root_here` + `still_present_on_HEAD` | Real when synth path open; also mirrors upstream record stalls until B3 rewrite |
| `budget_exhausted` | `downstream_of_homunculus_budget` + `still_present_on_HEAD` | Stage burned retries while incomplete/heal loops; symptom of thrash surface |
| Seated line missing WAV / vo_contract ladder | `root_here` | Feeds EDL + narrative `vo_g1` on all corpus masters |
| `thrash_detected` / `flush_refuse:vo_fail_open_not_success` | `root_here` | Fail-open vs heal-success chicken-egg still on HEAD (`heal_success` / flush path) |
| `edl_narrative:vo_g1` | `downstream_of_vo_synthesize` + `seed_order_noise` | HE-1 intentional when walk reaches audit early |
| AuthorityDenied on `transcripts/transition/*` | `authority_friction` | Pair transcript persist under freeze; secondary noise |
| gap_framing_recompose AuthorityDenied owner=`vo_synthesize` | `authority_friction` | Soft freeze after this stage stamps gap — foreign compose blocked |

Report why-high-risk: G1 / seed-order / budget; missing WAVs cascade into EDL

Classification values: `root_here` | `downstream_of_X` | `seed_order_noise` | `authority_friction` | `still_present_on_HEAD` | `healed`

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `stages/vo_synthesize.py::run_vo_synthesize` (~174 LOC) |
| Gate / Full-auto rewrite | `gap_vo_gates.require_vo_path_ready`, `rewrite_full_auto_record_lines_to_synth`; stability `delivery_guardrails.vo_synthesize_stability_block` |
| Transition synth | `transition_vo.synthesize_spoken_transitions`, `current_transition_pairs_missing`, `persist_vo_pair_gap` |
| Gap WAV resync | `stages/assembly.resync_required_synthesize_wavs` (nested staging dance) |
| Bind heal | `vo_bind_authority.heal_seated_bind_mismatch` (~313 LOC module) |
| EDL restamp | `transition_vo.restamp_edl_transition_source_paths`, `assembly.restamp_edl_vo_pickup_source_paths` |
| Assert + freeze | `vo_contract.assert_seated_vo_rendered`, `seat_authority.stamp_hard_seat_freeze` |
| Sanitize | `artifact_sanitize/vo_synthesize.py` (status + synthesis_report) |
| Done honesty | `stage_completion` vo_synthesize branch; `vo_synthesize_should_defer_done`; flush fail-open in `write_staging` |
| Freeze / ownership | ALLOW `vo_pickup/**`, status JSON; ALLOW gap stamp fields for `vo_synthesize`; nested VO under EDL lease |
| Tests (non local-ML) | `test_vo55_synthesize_authority.py`, `test_vo_path_ready.py`, `test_hv4_*`, `test_hv5_*`, `test_f2_seated_bind.py`, `test_artifact_sanitize_vo_bind.py`, `test_i10_hosted_vo_wav_coverage.py`, `test_transition_vo.py` |

---

## 4. Business-logic walk

1. **Happy** — ladder ready → (Full-auto) rewrite record→synth → omit stamp → transition + gap synth → promote → bind OK → restamp → report + assert + hard freeze → seed-complete.
2. **Incomplete** — any seated/G1/pair/bind-stale hole → incompleteness string; defer_done; reconcile clears hollow `.stage_done`.
3. **Refuse** — path not ready / no synth lines → SystemExit; freeze stamp fail → raise.
4. **Heal** — bind mismatch ladder; omit only when no stem anywhere (orientation never omitted); flush path may **fail-open** continue to edl/mix last-chance while stage stays incomplete.
5. **LLM ≤2** — N/A (local TTS; no OpenAI stage invoke).
6. **Done honesty** — B1 KEEP; `assert_seated_vo_rendered` fail-closed; sanitary/stale checks block seed_complete.

---

## 5. Over-engineering scorecard

### 5a — Baseline (investigate)

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **5** | (1) gate + Full-auto gap rewrite (2) transition WAV mint (3) gap WAV resync (4) bind heal + omit/plan mutate (5) EDL restamp + status/freeze seal |
| Dual / competing SSOTs | **yes** | Clinic map: transitions vs gap VO dual drive; status JSON vs `synthesis_report` vs on-disk WAV; G1 checklist vs seated bind |
| Soft-heal / thrash re-admit loops | **yes** | `heal_seated_bind_mismatch` re-admit; stability rewrite on probes; flush fail-open → mix last-chance; forensics `thrash_detected` + `vo_fail_open_not_success` |
| Co-producer / unpaid land | **yes** | Mutates `gap_report` delivery/omit, mastering_plan seats on omit, `master/edl.json` source_paths — ALLOW but non-primary books while claiming WAV ownership |
| Brittle predicates vs simple rules | **partial** | Stacked incompleteness (G1, pairs, seated, sanitary, hollow) is heavy but mostly named rules — not regex soup |
| Disproportionate shard/memo/resume | **no** | Nested staging for ownership is load-bearing; no missing_framing-style shard farm |
| “Fix everything downstream” behavior | **partial** | Fail-open continues walk; mix last-chance is intentional net — not full downstream craft rewrite |

**Over-engineered?** `yes` — responsibilities ≥4 and ≥2 hard fail-if rows (dual SSOT, soft-heal thrash, co-producer land).

**Scorecard verdict:** `FAIL`

- Flip to PASS: single responsibility “render required WAVs + refuse incomplete”; one readiness SSOT; no gap/plan/EDL mutate in this stage; delete heal-omit-as-progress and fail-open re-admit.

### 5b — Re-score after changes (MODE=fix)

| Check | Answer | Delta | Evidence now |
|-------|--------|-------|--------------|
| Responsibilities count | **2** | −1 (S6/S7) | (1) admit + omit-ledger stamp (2) one render job (`_render_required_vo_wavs`) + report/assert/hard freeze — orientation peeled to adjudicate |
| Dual / competing SSOTs | **no** | ↓ (S7) | Contract + helper treat gap + transitions as **one** spoken-render surface; soft inputs document seats/audit/ledger |
| Soft-heal / thrash re-admit loops | **partial** | same | One resynth attempt remains; no omit-as-success; honest approve pin |
| Co-producer / unpaid land | **partial** | same | Residual omit-ledger stamp only; no EDL/plan omit / delivery rewrite |
| Brittle predicates vs simple rules | **no** | same | `vo_synthesize_render_incompleteness` |
| Disproportionate shard/memo/resume | **no** | same | unchanged |
| “Fix everything downstream” behavior | **no** | same | S5 honest halt |

**Over-engineered?** `no` — responsibilities ≤2; dual SSOT cleared by accepting one render job; no hard fail-if remaining (soft-heal/co-producer are partial only).

**Scorecard verdict:** `PASS`

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | needs_you | **done** | `done:` peeled restamp from `run_vo_synthesize`; `run_edl` restamps transition+vo_pickup after `write_live_edl` | Co-producer unpaid land | `test_vo_synthesize_s1_s5_simplify.py::test_s1_*` |
| S2 | P0 | needs_you | **done** | `done:` heal refuses seated synth fail (no omit/plan unseat); WAV-accept + one resynth kept | Soft-heal thrash | `test_f2_seated_bind.py::test_heal_refuses_when_resynth_fails` |
| S3 | P0 | needs_you | **done** | `done:` Full-auto record→synth on `vo_line_adjudicate` (all paths); removed from `run_vo_synthesize`; stability rewrite kept as admit safety net | Responsibilities + dual policy | `test_s3_*` source pin |
| S4 | P1 | unambiguous | **done** | `done:` `vo_contract.vo_synthesize_render_incompleteness`; stage_completion thinned | Brittle stack | `test_s4_render_incompleteness_ssot` |
| S5 | P1 | needs_you | **done** | `done:` `approve_stage_writes` raises on deferred incompleteness (`action=halt`, no fail-open pass) | Soft-heal + fix-downstream | `test_s5_approve_incomplete_raises_not_fail_open` |
| S6 | P2 | needs_you | **done** | `done:` orientation retarget/revive on `vo_line_adjudicate._prep_opening_orientation`; removed from `run_vo_synthesize` | Responsibilities | `test_s6_*` + edl S3 pin updated |
| S7 | P2 | needs_you | **done** | `done:` accept one render job via `_render_required_vo_wavs` + contract soft inputs (no stage split) | Dual SSOT / count | `test_s7_*`; yaml soft seats/audit/ledger |

Status: `open` | `done` | `superseded` · Operator decisions (2026-09-25): safest S1–S5; **recommended S6→adjudicate; S7→accept one render (no split)**.

---

## 7. Root-cause verdict

Kitchen-sink peels S1–S7 landed. Stage is admit → one spoken render → seal. Residual partials (omit stamp, one resynth) are load-bearing honesty, not dual SSOTs. Missing WAVs remain a true product root for EDL/narrative.

---

## 8. Recommended next action

`leave` — scorecard **PASS** after S1–S7. Do not add heal layers.

---

## 9. Scope fence

Upstream poison owner (if any): `vo_line_adjudicate` (hollow text + orientation prep + record→synth), `nugget_layup_compose` / `gap_framing_compose` (seat/copy), G1 record policy  
Downstream victims (names only): `edl_narrative_audit`, `edl`, `sound_design_vo_finalize`, `mix`  
Did **not** redesign other stages (EDL restamp; adjudicate rewrite + orientation).
