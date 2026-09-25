# High-risk stage audit — edl

tier: T0 | seed: #58 | runs_hit: 9/9  
status: `complete`  
mode: fix  
updated: 2026-09-25T17:19:21Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

### What this stage does

Happy path: narrative audit not blocking → read disk selection (refuse uncommitted NLE) → read gap/transitions → refuse incomplete bridges → **`build_flow1_edl`** → refuse missing required VO WAVs / orientation contract → EDL + narrative QC → write `master/edl.json` → ledger → `post_edl` publishability → pair-freeze → refuse hollow mark_done → freeze air order.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `content_brief`, `coverage_audit`, `selection`, `edl_narrative_audit`, `transitions` | Contract hard |
| Reads (soft) | `gap_report`, `nugget_layup_plan`, bridges, omit/mastering as asserts | No mutate |
| Writes (SSOT) | `master/edl.json` | one_writer; assembly_ledger; air_order heal pin |
| Soft / side | Pair-freeze stamp; seating generation bump | No spoofed foreign writers (S2) |

### Rules that govern it

- **Admit** — selection speech order → EDL clips; seated synthesize VO must resolve; spoken transitions audible
- **Refuse** — narrative audit blocks; incomplete bridges → `transitions`; uncommitted NLE; missing required VO → `vo_synthesize`; orientation validate fail; schema; publishability; G1/VO hollow
- **Incomplete** — G1 / VO seed / sanitary / orientation inaudible via `stage_completion`
- **Heal** — none inside stage after S1–S5 (upstream owns VO/glue/orientation)
- **Wait_for_gate** — G1 via incompleteness
- **Done / hollow honesty** — `heal_or_refuse_mark` + G1/VO SystemExit
- **Hard floors** — edl_qc / narrative_qc / validate_opening_orientation / post_edl
- **Freeze / ownership** — not a selection/gap/transitions producer; DENY VO mint as `edl`

### Considerations & load-bearing policy

- Selection leads EDL; NLE must already be on disk selection.
- Missing VO / orientation ensure / seam glue live on `vo_synthesize` / `transitions`.
- Full-auto: late refuse is cheaper than nested kitchen remaster.

### LLM / external calls

- No LLM. No nested S2S from EDL after S1 (WAV mint is `vo_synthesize`).

### What it deliberately does *not* do

- Nested VO resynth / bind heal (S1)
- Spoofed layup/transitions writes (S2)
- Orientation ensure/retarget/revive (S3 → `vo_synthesize`)
- Seam glue mint / transition synth (S4 → `transitions` / `vo_synthesize`)
- Blank/chapter/air-script selection dual-copy (S5)

### Operator-visible effects

- Blocks mix when WAV/orientation/QC/bridges fail
- Uncommitted NLE → SystemExit to land selection first

---

## 1. Job statement

Lock the hearable timeline: build `master/edl.json` from disk selection + already-seated VO/transition audio, then refuse if anything required is missing or inaudible.

---

## 2. Error-hint intake

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| Gap VO lines missing WAV | `downstream_of_vo_synthesize` | Hard refuse only (S1 peeled nested resynth) |
| `opening_orientation_inaudible` | `downstream_of_vo_synthesize` (ensure) + gate here | Validate-only in EDL (S3) |
| Freeze vs nugget_layup_plan | `authority_friction` healed for EDL path | Spoofed adopt removed (S2); assert_layup_fresh remains |
| `selection_edl_order_drift` | `still_present_on_HEAD` reduced | No blank/chapter dual-copy; uncommitted NLE refused (S5) |
| Incomplete bridges | `downstream_of_transitions` | Refuse → transitions (S4) |

Report why-high-risk: Missing VO WAVs, opening_orientation, freeze ownership

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_*` | `stages/assembly.py::run_edl` |
| Timeline build | `build_flow1_edl` |
| VO resolve (read) | `resolve_vo_pickup_path` (no nested mint) |
| Glue preflight | `missing_reorder_bridges` / `assert_bridges_complete` (no mint) |
| Orientation | `validate_opening_orientation` only |
| Upstream ensure | `vo_synthesize` retarget/revive; `transitions` `ensure_seam_glue` |
| Tests | `test_edl_s1_s5_simplify.py` + prior EDL suite |

---

## 4. Business-logic walk

1. **Happy** — audit clear → disk selection (+ committed NLE) → bridges complete → build → QC → write → mark_done → freeze.
2. **Incomplete** — G1/VO/orientation hollow at mark_done.
3. **Refuse** — narrative block; bridges missing; NLE not on disk; missing VO; orientation contract; schema; publishability.
4. **Heal** — none in-stage (S1–S5).
5. **LLM** — N/A.
6. **Done honesty** — incompleteness SystemExit + `heal_or_refuse_mark`.

---

## 5. Over-engineering scorecard

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **7** | Pre-S1–S5 baseline |
| Dual / competing SSOTs | **yes** | Pre-simplify |
| Soft-heal / thrash re-admit loops | **yes** | Pre-simplify |
| Co-producer / unpaid land | **yes** | Pre-simplify |
| Brittle predicates vs simple rules | **yes** | Pre-simplify |
| Disproportionate shard/memo/resume | **partial** | Pre-simplify |
| “Fix everything downstream” behavior | **yes** | Pre-simplify |

**Over-engineered?** `yes`  
**Scorecard verdict:** `FAIL` (baseline §5a)

### 5b — Re-score after changes (MODE=fix 2026-09-25T17:19:21Z)

HEAD: `run_edl` cut-only; orientation on `vo_synthesize`; seam glue on `transitions`; `test_edl_s1_s5_simplify.py` green (9).

| Check | Answer | Fail-if? | Evidence now |
|-------|--------|----------|--------------|
| Responsibilities count | **2** | no | (1) build timeline from disk inputs (2) hard QC / refuse / freeze. NLE gate is refuse, not heal |
| Dual / competing SSOTs | **no** | no | Disk selection SSOT; no blank/chapter dual-copy; no spoofed writers |
| Soft-heal / thrash re-admit loops | **no** | no | No nested VO/transition synth; no orientation ensure/revive |
| Co-producer / unpaid land | **no** | no | No `nugget_layup_compose` / `transitions` spoof; no gap commit kitchen |
| Brittle predicates vs simple rules | **partial** | no | Optional-skip filter on missing_vo + dual orientation validate sites remain |
| Disproportionate shard/memo/resume | **partial** | no | `build_flow1_edl` + helpers still large; stage body peeled |
| “Fix everything downstream” behavior | **no** | no | Refuse → `vo_synthesize` / `transitions` / selection owner |

**Fail-if hits:** 0  
**Over-engineered?** `no`  
**Scorecard verdict: PASS**

What flipped FAIL → PASS: S1–S5 peel (kitchen out; cut + refuse in).

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | unambiguous | **done:** nested VO/transition synth removed from `run_edl` | soft-heal; fix-downstream; responsibilities | missing WAV refuse only |
| S2 | P0 | unambiguous | **done:** no spoofed layup/transitions stage_keys | unpaid land; dual SSOT | source inspect tests |
| S3 | P0 | needs_you → **decided: vo_synthesize** | **done:** ensure/retarget/revive on `vo_synthesize`; EDL validate-only | responsibilities; soft-heal | vo_synthesize source contains retarget/revive |
| S4 | P1 | needs_you → **decided: transitions** | **done:** `ensure_seam_glue` on `run_transitions`; EDL bridge refuse only | responsibilities; fix-downstream | transitions source contains ensure_seam_glue |
| S5 | P1 | unambiguous | **done:** no blank/chapter/air-script persist; uncommitted NLE SystemExit | dual SSOT; unpaid land | NLE test expects refuse |

**Open ship rows:** none.  
**Operator decisions recorded:** S3 → `vo_synthesize`; S4 → `transitions`.  
**Backlog:** collapse dual orientation validate (build + stage_done); tighten mark_done except-path soft `mark_done`.

---

## 7. Root-cause verdict

Pre-simplify EDL was a delivery kitchen. After S1–S5 it is a **cut + refuse** stage: disk selection + seated audio → `master/edl.json`, else pin upstream owners. Residual brittleness is optional-skip / dual validate — not scorecard fail-if.

---

## 8. Recommended next action

`leave`

---

## 9. Scope fence

Upstream poison owner (if any): `vo_synthesize` / G1; `transitions` / seam glue; selection owner for NLE  
Downstream victims (names only): `assembly_preview`, `junction_snip_qa`, `mix`, `master_finalize`, `listen_delight_audit`  
Did **not** redesign other stages beyond parking S3/S4 ownership hooks on `vo_synthesize` / `transitions`.
