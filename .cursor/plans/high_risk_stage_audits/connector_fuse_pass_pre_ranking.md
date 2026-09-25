# High-risk stage audit — connector_fuse_pass_pre_ranking

tier: T1 | seed: #39 | runs_hit: 9/9  
status: `complete`  
mode: fix  
updated: 2026-09-25T18:05:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> Delivery-side **second connector fuse** immediately before `full_master_ranking`. Same shared fuse engine as analysis `connector_fuse_pass`, but `pass_id=pre_ranking` so writer identity, LLM tier, and settle rules differ. Job: fuse unfinished adjacent speech seams (and rewrite the segment lattice) so ranking sees honest boundaries — not invent selection or heal gap VO.

### What this stage does

Happy path: soft-read prior fuse audit / hitch → `run_connector_fuse_pass(pass_id="pre_ranking")` → enumerate adjacent seams → skip settled stay_independent unless seam_hash or chapter membership changed → LLM adjudicate (standard tier) → apply fuses → rewrite `segments/manifest.json` + `boundaries.json` + full `seg_*` id remap (incl. `transcripts/index.json` with `mutation_class=segment_id_remap`) → stamp **`analysis/connector_fuse_rounds_pre_ranking.json`** → `heal_or_refuse_mark`. HV cluster / diar forced / air-bounds / encompass / split-island QC are analysis-only (S2/S3 peel).

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `segments/manifest.json` | S5 contract hard |
| Reads (soft) | `transcript/full.json`, `analysis/low_conf_islands.json`, `analysis/connector_fuse_audit.json`, `mastering/chapter_close_hitch.json` | Settlement + context |
| Writes (SSOT) | `analysis/connector_fuse_rounds_pre_ranking.json` | S1 dedicated path (not shared with analysis) |
| Co-writes | `segments/manifest.json`, `segments/boundaries.json`, `analysis/connector_fuse_audit.json`, seam packets/verdicts | ALLOW; settle uses audit |
| Remap / integrity | `transcripts/index.json` + `SEGMENT_ID_REMAP_PATHS` | Ops path; paid with `mutation_class=segment_id_remap` |

### Rules that govern it

- **Admit** — fuse enabled (Full-auto forces on); manifest present; seed must-precede arc → hitch
- **Refuse** — junction_heal reopen gate (other stage); oscillation halt records residual (no infinite)
- **Incomplete** — missing/unreadable rounds; `pass_id != pre_ranking`; `skip_reason=missing_manifest`
- **Heal** — `heal_or_refuse_mark` after real outputs; no soft success on hollow rounds
- **Wait_for_gate** — none (G-Framing/G1 are upstream)
- **Done / hollow honesty** — outputs present only when rounds stamped `pre_ranking` and not missing_manifest (HS-3 / H6-B)
- **Hard floors** — incomplete-thought fuse only; pre_ranking never prefer-fuse on uncertain clean seams (H2-A)
- **Freeze / ownership** — ALLOW remaps under freeze; ops `transcripts/index` needs mutation_class

### Considerations & load-bearing policy

- Must precede ranking in `MUST_PRECEDE` / `PRE_RANKING_SEED_CHAIN` (arc → hitch → this → ranking).
- Settle prior analysis stay_independent unless hash/chapter changed — avoids re-LLM thrash.
- Publishability: selection still leads; this only cleans segment graph before ranking.
- Full-auto: fuse cannot stay disabled (H6-C).

### LLM / external calls

Prompt `segmentation/connector-seam-adjudicate.system.txt` via shared `adjudicate_seams` — pre_ranking **standard** tier (analysis economy). Deterministic fallback on LLM fail. Homunculus ≤2 attempts per stage invoke.

### What it deliberately does *not* do

- Own ranking / selection membership / gap report
- Own junction incomplete-cut repair (`junction_heal` is a different pass_id / stage)
- Invent VO or framing
- Replace analysis `connector_fuse_pass` audit as the only fuse ever (analysis still first)
- Run HV cluster / diar forced / air-bounds / encompass / split-island QC (S2/S3 — analysis-only)

### Operator-visible effects

- Blocks ranking / gap_report_sanitize / refinement when incomplete (seed-order)
- `delivery:premature_complete:stage:connector_fuse_pass_pre_ranking` when walker advances past hollow/incomplete pass
- No operator gate of its own

---

## 1. Job statement

Before full-master ranking, re-adjudicate unsettled (or hash/chapter-changed) adjacent seams and fuse unfinished thoughts into the live segment lattice, stamping a dedicated `pass_id=pre_ranking` rounds doc so ranking cannot leapfrog a hollow first-pass fuse.

---

## 2. Error-hint intake

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `delivery:premature_complete:stage:connector_fuse_pass_pre_ranking` | `root_here` + `still_present_on_HEAD` | Walker marks delivery ahead while rounds missing / mid-fail; lighter path after S1–S5 should shrink storms |
| `authority_denied:persist:transcripts/index.json:…:pre_soft_freeze:ops` | `healed` (G1) | mutation_class + ALLOW |
| `thrash_detected` | `downstream_of_X` + `seed_order_noise` | Often waiting on arc/hitch |
| Seed-order: complete `narrative_arc_plan` before this | `downstream_of_narrative_arc_plan` / `seed_order_noise` | MUST_PRECEDE |
| Seed-order: complete this before gap_report / refinement | `seed_order_noise` | Victims waiting on paid rounds |
| `fuse_oscillation` / residual | `root_here` (bounded) | Cap + pin (HS-4) |

Report why-high-risk: Premature delivery complete; transcript authority

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry | `stages/low_conf_fuse_stages.py` → `pass_id="pre_ranking"` |
| Shared body | `segment_fuse.run_connector_fuse_pass` (pre_ranking peels HV/diar/lattice) |
| Rounds SSOT | `FUSE_ROUNDS_PRE_RANKING_PATH` via `fuse_rounds_path` |
| Settle + remap | `select_pending_seam_packets`, `apply_full_segment_id_remap` |
| Done honesty | `_pre_ranking_fuse_incompleteness`, `_pre_ranking_rounds_present` |
| Tests | `test_cfp_pre_ranking_s1_s5_simplify.py`, harden / HS-3 / HS-4 |

---

## 4. Business-logic walk

1. **Wrapper** — `run_connector_fuse_pass(ctx, pass_id="pre_ranking")`; heal stamps writer stage.
2. **Enable / skip** — Full-auto force-on else skip to dedicated pre_ranking rounds path (no analysis audit stub); missing manifest → incomplete.
3. **Seam loop only** — S2/S3: no HV, no diar, no air/encompass/split on pre_ranking.
4. **Apply** — settle → LLM adjudicate → fuse until fixed point / cap / oscillation.
5. **Integrity** — manifest + boundaries + id remap + speech sidecars (S4 kept).
6. **Done** — dedicated rounds with `pass_id=pre_ranking`; analysis rounds cannot satisfy (S1).

---

## 5. Over-engineering scorecard

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **4** | *(baseline)* seam + HV/diar + remap + lattice QC |
| Dual / competing SSOTs | **yes** | *(baseline)* shared rounds.json |
| Soft-heal / thrash re-admit loops | **no** | Oscillation halts; no soft hollow success |
| Co-producer / unpaid land | **no** | Index remap ALLOW + mutation_class |
| Brittle predicates vs simple rules | **partial** | *(baseline)* pass_id on shared path |
| Disproportionate shard/memo/resume | **yes** | *(baseline)* full kitchen on pre_ranking |
| “Fix everything downstream” behavior | **yes** | *(baseline)* air/encompass/split QC |

**Over-engineered?** `yes` — baseline FAIL.

**Scorecard verdict:** `FAIL`

### 5b — Re-score after changes (MODE=fix)

| Check | Answer | Delta | Evidence now |
|-------|--------|-------|--------------|
| Responsibilities count | **2** | 4→2 | settle→adjudicate→apply; remap + dedicated rounds |
| Dual / competing SSOTs | **no** | yes→no | `FUSE_ROUNDS_PRE_RANKING_PATH`; analysis rounds DENY |
| Soft-heal / thrash re-admit loops | **no** | — | unchanged |
| Co-producer / unpaid land | **no** | — | S4 kept |
| Brittle predicates vs simple rules | **no** | partial→no | Manifest hard (S5); dedicated path |
| Disproportionate shard/memo/resume | **no** | yes→no | HV/diar/lattice skipped on pre_ranking |
| “Fix everything downstream” behavior | **no** | yes→no | Lattice QC peeled; remap integrity only |

**Over-engineered?** `no`

**Scorecard verdict:** `PASS`

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | unambiguous | **done** | `done:` dedicated `connector_fuse_rounds_pre_ranking.json` + ownership/agenda/incompleteness/dispatch/FMR soft | Dual SSOT | Analysis rounds cannot satisfy |
| S2 | P0 | needs_you | **done** | decided **recommended**: skip HV + diar on pre_ranking | Responsibilities; disproportionate | `skipped: pre_ranking_peel` |
| S3 | P0 | needs_you | **done** | decided **recommended**: peel air/encompass/split QC | Fix-downstream; responsibilities | Apply + remap + rounds only |
| S4 | P1 | unambiguous | **done** | `done:` keep settle + id remap + mutation_class | (preserve) | G1/G3 + S4 tests green |
| S5 | P2 | needs_you | **done** | decided **hard manifest** in contract | Brittle | `test_s5_contract_manifest_is_hard` |

Operator decisions: pick all S1–S5 with recommended options (2026-09-25). Open rows: none.

---

## 7. Root-cause verdict

Baseline FAIL was inherited multi-mode kitchen + shared rounds SSOT. After S1–S5, pre_ranking is settle→fuse→remap→dedicated rounds; analysis still owns HV/diar/lattice QC.

---

## 8. Recommended next action

`leave` — scorecard PASS after S1–S5; monitor premature_complete on next full-auto.

---

## 9. Scope fence

Upstream poison owner (if any): `narrative_arc_plan` / `chapter_close_hitch` when must-precede incomplete.  
Downstream victims (names only): `full_master_ranking`, `gap_report_sanitize`, `refinement_agenda`, `nugget_layup_compose`.  
Did **not** redesign other stages.
