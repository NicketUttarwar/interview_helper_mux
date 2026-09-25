# High-risk stage audit — selection_framing_apply

tier: T1 | seed: #49 | runs_hit: 8/9  
status: `complete`  
mode: fix  
updated: 2026-09-25T18:05:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Write this before anything else. Also open the chat with a short spoken summary of what this stage does, its main rules, and key considerations so a human can orient cold.

### What this stage does

Happy path (deterministic Pass-2 apply): seat-mutation gate → ensure gap_report is authoritative → validate `master/selection.json` → `decide_pass` must **activate** (else skip stub) → apply framing VO-cover excludes via `commit_selection_mutation` (reason `covered_by_framing_vo`) when `validate_framing_ranking` has no hard issues → stamp-only gap seat sync (`stamp_gap_seats_to_selection`: retarget `targets_segment_id` or omit off-timeline lines) → write apply sidecar → mark done only if gap stays W1-sanitary.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `master/selection.json`, `understanding/gap_report.json` | Contract; selection must exist/be a dict |
| Reads (soft) | gap_framing_plan, … | Cover excludes |
| Writes (claimed SSOT) | `understanding/selection_framing_apply.json` | Skip / refuse / applied stub |
| Co-writes (ALLOW producer) | `master/selection.json` | Framing excludes via commit only (SFA-S2) |
| Co-writes (stamp) | `understanding/gap_report.json` | Retarget / omit stamps only (SFA-S1) |

### Rules that govern it

- **Admit** — seat mutation permitted; selection present + dict; decide_pass activate; Pass-2 gap stays sanitary at finish
- **Refuse** — `missing_selection` / `invalid_selection` stubs (no heal); `gap_unsanitary` at `_finish_pass2`
- **Incomplete** — refused APPLY never seed-completes (SFA-B2); gap_unsanitary; pending sidecar
- **Heal** — seat-freeze / decide_pass skip: skip stub + `_heal_pass2`; sanitary applied path heals after sidecar
- **Wait_for_gate** — none owned
- **Done / hollow honesty** — HF-1 skip stub; refused never seed-complete; HF-5 gap dirty blocks done
- **Hard floors / QC bars** — `validate_framing_ranking` hard strings; W1 gap sanitary at finish
- **Freeze / never_touch / ownership** — seat freeze → no-op; selection producer ALLOW includes apply; gap stamp AllowRow (no body text)

### Considerations & load-bearing policy

- Lattice priority **last**: framing VO-cover excludes (`selection_constraints` #6) — kept here (S5 safest: leave, do not delete_path / peel to ranking which only restores primaries).
- Ledger heat mostly seed-order behind `#45 nugget_layup_compose`.
- Full-auto: deterministic; no LLM.

### LLM / external calls

N/A (deterministic).

### What it deliberately does *not* do

- No orientation / layup restore / clone-adjacency / contiguous-bridge body heal
- No hosted VO floor persist
- No post_framing selection sanitize thrash
- No VO WAV / EDL / ranking primary order

### Operator-visible effects

- Blocks air_script_seams / VO ladder when incomplete
- Seat freeze / decide_pass skip → skip stub + done

---

## 1. Job statement

Apply framing VO-cover membership onto live selection (exclude covered natives), then stamp-only retarget/omit gap VO seats onto the surviving air timeline and land an honest apply sidecar without hollow Pass-2 done.

---

## 2. Error-hint intake

From the high-risk report. Classify each predicate.

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `seed_order_prereq` / complete `nugget_layup_compose` before apply | `seed_order_noise` + `downstream_of_X` (`nugget_layup_compose`) | Dominant in exec_13198 |
| complete `air_script_compose` / `selection_order_sanitize` before apply | `seed_order_noise` | Sparse |
| `hosted_vo_floor_*` | `downstream_of_X` (layup / framing) | Peeled from apply (S4) |
| selection thrash / AuthorityDenied | `healed` (local unpaid) / residual `authority_friction` | S2 producer ALLOW + commit path |
| `gap_unsanitary` / resume selection_framing_apply | `still_present_on_HEAD` | HF-5 intentional honesty |
| Blocked on layup incomplete (report why) | `downstream_of_X` (`nugget_layup_compose`) | Report §#49 |

Report why-high-risk: Blocked on layup incomplete; selection thrash

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `refinement_passes.py::run_selection_framing_apply` |
| Skip / refuse stubs | `persist_pass2_skip_stub`, `persist_apply_refuse_stub`, `persist_pass2_refuse_stub` |
| Finish / heal | `_finish_pass2`, `_heal_pass2` |
| Cover exclude | `ranking_exclude_segment_ids` → `commit_selection_mutation` (producer=apply) |
| Gap seat sync | `gap_framing.stamp_gap_seats_to_selection` |
| Gate | `decide_pass` — **honored** (S3 skip = no mutate) |
| Done honesty | SFA-B2 refuse + HF-5 gap sanitary |
| Ownership | APPLY sidecar; selection producers include apply; gap stamp AllowRow |
| Contract | `docs/cross-cutting/stage-contracts/selection_framing_apply.yaml` |
| Tests | `test_sfa_s1_s5_simplify.py`, HF-1/HF-5, `test_i15_…` stamp ALLOW |

---

## 4. Business-logic walk

**Happy:** seat OK → selection dict → decide_pass activate → framing excludes via commit if no hard validate → stamp gap seats → `{applied}` → `_finish_pass2` sanitary → heal.

**Seat freeze / gate error:** skip stub → heal → return.

**decide_pass skip:** skip stub (`reason_code`) → heal → return (no selection/gap mutate).

**Missing / invalid selection:** refuse stub → no mark_done (checked **before** decide_pass).

**Hard framing validate:** skip exclude commit; still stamp gap + sidecar.

**Gap dirty at finish:** refuse stub + raise resume self (HF-5).

**LLM:** none.

---

## 5. Over-engineering scorecard

### 5a — Baseline (pre S1–S5)

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **6** | exclude · gap heal chain · sanitize · floor · gate ornamental · sidecar |
| Dual / competing SSOTs | **yes** | APPLY vs selection+gap |
| Soft-heal / thrash re-admit loops | **partial** | restore_layup / sanitize thrash |
| Co-producer / unpaid land | **yes** | selection not producer; gap body restores |
| Brittle predicates vs simple rules | **partial** | hard validate strings; decide_pass bypass |
| Disproportionate shard/memo/resume | **no** | |
| “Fix everything downstream” behavior | **yes** | orientation + layup + floor + sanitize |

**Over-engineered?** `yes`  
**Scorecard verdict:** `FAIL` (baseline)

### 5b — Re-score after changes (MODE=fix 2026-09-25T18:05:00Z)

| Check | Answer | Fail-if? | Evidence now |
|-------|--------|----------|--------------|
| Responsibilities count | **2** | no | (1) lattice #6 framing exclude commit (2) stamp-only gap seat sync + sidecar honesty |
| Dual / competing SSOTs | **partial** | no | APPLY proof sidecar + intentional lattice #6 / stamp seats (ALLOW producer; S9 stamp-safe) |
| Soft-heal / thrash re-admit loops | **no** | no | No restore/orientation/clone/sanitize thrash; skip is honest |
| Co-producer / unpaid land | **no** | no | selection producer ALLOW; gap stamp-only (no text rewrite) |
| Brittle predicates vs simple rules | **partial** | no | Hard validate string sniff remains |
| Disproportionate shard/memo/resume | **no** | no | |
| “Fix everything downstream” behavior | **no** | no | Floor / body heal / post_framing sanitize peeled |

**Fail-if hits:** 0  
**Over-engineered?** `no`  
**Scorecard verdict:** `PASS`

What would flip FAIL → PASS: _(cleared)_ optional backlog: simplify hard-validate strings; heal_pin allowlist for HF-5 `heal_navigate` (pre-existing Clinic E refuse — out of stage body scope).

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | unambiguous | **done** | `done:` `stamp_gap_seats_to_selection`; peeled restore/orientation/clone/drop/rebase | responsibilities, fix-downstream, co-producer | `test_sfa_s1_s5_simplify.py::test_s1_*` |
| S2 | P0 | unambiguous | **done** | `done:` producer ALLOW + `commit_selection_mutation` only; no post_framing sanitize | dual SSOT / unpaid land | `test_s2_*` |
| S3 | P1 | unambiguous | **done** | `done:` decide_pass ≠activate → skip stub, no mutate | brittle / responsibilities | `test_s3_*` |
| S4 | P1 | needs_you | **done** | `done:` peeled `identify_hosted_vo_floor` (already on layup/framing/VO) | fix-downstream | `test_s4_*` |
| S5 | P2 | needs_you | **done** | `done:` **leave** exclude here (lattice #6); ranking `enforce_framing_ranking` only restores primaries — do not delete_path | dual SSOT / leave | `test_s5_*` |

Operator decisions (2026-09-25): **all safest** — S1 stamp-only; S2 commit+ALLOW (not peel exclude upstream); S3 honor skip; S4 peel floor only; S5 leave exclude in apply (not delete_path).

Open rows: none (PASS). Optional backlog: heal_pin allowlist for Pass-2 `gap_unsanitary` → `selection_framing_apply` (`heal_navigate` currently Clinic-E refuses).

---

## 7. Root-cause verdict

S1–S5 landed. Apply is lattice #6 exclude commit + stamp-only gap seats. Ledger heat remains mostly seed-order behind layup; local unpaid co-write / fix-downstream healed.

---

## 8. Recommended next action

`leave` — scorecard **PASS** after S1–S5. Do not add heal layers.

---

## 9. Scope fence

Upstream poison owner (if any): `nugget_layup_compose` (seed-order / floor / gap body)  
Downstream victims (names only): `air_script_seams`, VO contract ladder, `gap_report_sanitize`, EDL seating  
Did **not** redesign other stages.
