# High-risk stage audit — chapter_close_hitch

tier: T1 | seed: #38 | runs_hit: 3/9  
status: `complete`  
mode: fix  
updated: 2026-09-25T18:20:00Z

**Report:** `.cursor/plans/high_risk_error_stages_report.md`  
**Write this file** for the investigation. When complete, update **only this stage’s row** in the report’s `## Audit findings` table.

---

## §0 — Stage Guide (REQUIRED FIRST)

> One-shot host after the first `narrative_arc_plan`: freeze that chapter map, recut keepers to the last listen-complete hinge inside chapter/TP bounds, republish boundaries (new `seg_*` allowed), remap every consumer, optionally restage a long inner walk through a second narrative plan (QC), then latch forever. Not a second ranking or VO author — but HEAD still co-writes many shared primaries as “integrity.”

### What this stage does

Happy path: require live `master/narrative_plan.json` (or frozen `intent_plan`) → snapshot pre-keepers / VO / omit → compute recut windows (listen-complete + hanging extend + same-speaker merge + acoustic edge refine) → publish `segments/boundaries.json` + hitch keepers + remap → rewrite `SHARED_REMAP_RELS` (+ intent) with `mutation_class=segment_id_remap` → bounded invalidation / unmark restage window (or remap-only if Phase A / assembly seated) → **inner walk** `boundary_detection` → `narrative_arc_plan` (skip boundary recollate when hitch already published) → refresh live remap → post-walk patches (VO rebind/reattach, omit, chapter authority onto narrative, episode_structure align, layup adopt, ranking-lattice unmark or sanitize restamp) → latch `status=committed` → `heal_or_refuse_mark`.

### Primary artifacts

| Role | Path | Notes |
|------|------|-------|
| Reads (hard) | `master/narrative_plan.json` | Frozen into intent; seed-order refuse if missing |
| Writes (SSOT) | `mastering/chapter_close_hitch.json` | Latch; one-shot commit |
| Writes (owned shards) | `mastering/chapter_close_hitch/{intent_plan,remap,pre_keepers,hitch_keepers,vo_snapshot,omit_ledger}.json`, `master/narrative_plan.qc.json` | Operational / hitch prefix |
| Co-writes | `segments/boundaries.json`, `master/narrative_plan.json` (`hitch_chapter_authority`), `understanding/ideal_cuts_materialized.json` (full snapped cuts under remap class), `SHARED_REMAP_RELS` (gap_report, selection, …), episode_structure (+ compact) | ALLOW remaps / co-producer rows |
| Soft / side | G1 `vo_pickup` WAV stem copies; ranking-lattice `.stage_done` clear or sanitize restamp | HR-1 |

### Rules that govern it

- **Admit** — `mastering.chapter_close_hitch.enabled` (default on); narrative plan or intent present; latch not already `committed`
- **Refuse** — missing narrative/intent → `RuntimeError` seed-order (no hollow skip); layup adopt fail → leave latch `running`, raise pin to `nugget_layup_compose`
- **Incomplete** — `hitch_layup_adopt_failed` in latch (`stage_completion`); running latch without commit
- **Heal** — `heal_or_refuse_mark` only after committed latch (or disabled skip); resume path skips second recut when `status=running` + wiped + remap/boundaries exist
- **Wait_for_gate** — none of its own; inner walk **auto-confirms** pending G-Framing / pickup speaker via hitch as ALLOW co-owner of `flow_adaptation`
- **Done / hollow honesty** — committed latch required; cannot skip until latch committed; adopt-fail refuses hitch complete
- **Hard floors** — zero-duration windows dropped; overlap clamped; must-keep remap unmatched tracked; never nuclear `clear_from` whole pipeline (B-05 bounded profiles)
- **Freeze / ownership** — narrative adopt requires `mutation_class=hitch_chapter_authority`; remaps require `segment_id_remap`; anti-spoof blocks hitch claiming `narrative_arc_plan` stage_key; late edl/mix/VO never unmarked

### Considerations & load-bearing policy

- Must sit in pre-ranking seed chain: arc → **hitch** → connector_fuse_pre_ranking → ranking (`MUST_PRECEDE` / consumers).
- First cut pass cannot see chapters — hitch is the chapter-aware recut (canon: `docs/cross-cutting/mastering-process.md`).
- Phase A / assembly seated → remap-only (no ranking rewind); else unmark ranking lattice (selection / gap sanitize / layup / air_script).
- Publishability: selection still leads after remapped ids; hitch must not invent selection membership (layup adopt is rebind, not rank).
- Full-auto: hitch enabled by default; listen_restage armed at most once (C14 timeline reopen gate after assembly).

### LLM / external calls

N/A for hitch body (deterministic + acoustic refine). Inner walk may invoke nested stage LLMs; budget billed as hitch via `_chapter_close_hitch_inner` / `hitch_budget_identity`. Homunculus ≤2 attempts per outer invoke.

### What it deliberately does *not* do

- Own primary ranking / selection order policy
- Author gap VO copy or synthesize WAVs (rebind/reattach only)
- Junction millimetre QA / mix / EDL (forbidden late unmark set)
- Re-run forever (latch `committed` = no-op)

### Operator-visible effects

- Blocks pre-ranking consumers (`connector_fuse_pass_pre_ranking`, ranking, gap_report_sanitize, refinement) until latch committed (seed-order)
- Can flip `_meta.producer_stage` on remapped shared paths → unpaid-land thrash on sanitize stages
- No dedicated GUI gate; listen_restage is programmatic (delight / reopen)

---

## 1. Job statement

After the first narrative chapter map, one-shot recut keepers to chapter/TP listen-complete closes, remint the segment contract + id map, restage enough upstream to re-bind live ids, adopt remapped chapters onto `narrative_plan`, and latch so ranking never sees pre-hitch ends.

---

## 2. Error-hint intake

| Predicate / error | Classification | Notes |
|-------------------|----------------|-------|
| `authority_denied:persist:understanding/ideal_cuts_materialized.json:chapter_close_hitch:… (mutation_class_required:segment_id_remap)` | `healed` (class) / still `root_here` (content) | exec_13159: write lacked mutation_class. HEAD passes `mutation_class=segment_id_remap` but still **replaces cuts** with hitch snapped corpus — remap class used as content-author cover |
| Ideal-cuts / boundaries co-publish after hitch | `authority_friction` + `still_present_on_HEAD` | Hitch stamps `publisher_stage=chapter_close_hitch` on boundaries; also writes materialized cuts |
| Id remap cascades (SHARED_REMAP_RELS + VO stems) | `root_here` + intentional | Required integrity; cascades into ranking / sanitize / narrative consumers |
| `shared-path unpaid land … gap_report.json producer_stage='chapter_close_hitch'` | `root_here` + `still_present_on_HEAD` | exec_13198; hitch remap/reattach stamps producer; `gap_report_sanitize` co-producer allowlist does **not** include hitch |
| Seed-order: complete hitch before refinement / gap_report_sanitize | `seed_order_noise` | Victims waiting on latch — correct clamp when hitch incomplete |
| `hitch_layup_adopt_failed` → resume layup | `root_here` (bounded) | Honest incomplete; HR-1 pins layup not hitch |

Report why-high-risk: Ideal-cuts authority; id remap cascades

---

## 3. Code surface map

| Piece | Location |
|-------|----------|
| Entry `run_chapter_close_hitch` | `src/interview_mux/chapter_close_hitch.py` ~L1663 (~1989 LOC module) |
| Recut core | `compute_recut_windows`, `last_listen_complete_end_ms`, `apply_acoustic_refine`, `reapply_same_speaker_keep_merge` |
| Boundaries + remap | `_publish_boundaries_from_windows`, `build_segment_remap`, `refresh_live_remap` |
| Shared rewrite | `rewrite_upstream_segment_refs` → `segment_id_remap.rewrite_artifact_segment_refs` |
| Inner walk | `run_inner_walk` / `hitch_restage_order` (24 stages: boundary_detection → narrative_arc_plan) |
| Post patches | `apply_post_walk_patches`, `apply_chapter_authority`, `reattach_vo_to_gap_report`, layup `adopt_layup_plan_to_selection` |
| Ranking lattice | `apply_hitch_ranking_lattice_after_remap` (unmark vs restamp) |
| Freeze / ownership | `artifact_ownership` ALLOW hitch latch/shards; remap stages on `SEGMENT_ID_REMAP_*`; narrative `hitch_chapter_authority`; anti-spoof |
| Contract | `docs/cross-cutting/stage-contracts/chapter_close_hitch.yaml` |
| Tests (non local-ML) | `test_chapter_close_hitch.py`, `test_hr1_hitch_ranking_lattice.py`, `test_hitch_thought_continuity.py` |

---

## 4. Business-logic walk

**Happy:** narrative present → latch running → windows recut → boundaries+remap published → refs rewritten (incl. full materialized rewrite) → bounded invalidation / unmark restage order → inner walk (skip boundary LLM if hitch contract) → live remap refresh → chapter authority write + VO/omit/structure/layup patches → lattice unmark or sanitize restamp → latch committed → mark done.

**Incomplete / refuse:** no narrative/intent → seed-order raise; layup adopt `ok=False` → latch stays running + raise `hitch_layup_adopt_failed` (completion probes pin layup).

**Heal (bounded):** resume skips recut when wiped+remap+boundaries; disabled config commits skipped latch; listen_restage once via `arm_hitch_listen_restage` (C14 fail-closed after assembly).

**LLM ≤2:** hitch body N/A; nested stages use hitch budget identity.

**Done honesty:** committed latch or disabled skip; adopt-fail blocks seed-complete / heal navigate to layup.

---

## 5. Over-engineering scorecard

### 5a — Baseline (investigate)

| Check | Answer | Evidence |
|-------|--------|----------|
| Responsibilities count (ideal 1; flag ≥3) | **6** | (1) listen-complete recut+acoustic (2) boundaries/id remap (3) 24-stage inner restage (4) chapter authority / QC adopt (5) VO+omit+layup+structure kitchen (6) ranking-lattice unmark/restamp + gate auto-confirm |
| Dual / competing SSOTs | **yes** | Latch vs live narrative vs QC plan; hitch-published boundaries vs ideal_cuts_materialize ownership; materialized rewritten as hitch cuts under remap mutation |
| Soft-heal / thrash re-admit loops | **partial** | Latch prevents double hitch; lattice unmark re-admits ranking chain by design; resume/listen_restage bounded — not infinite soft-heal |
| Co-producer / unpaid land | **yes** | Remap stamps `producer_stage=chapter_close_hitch` on `gap_report` (exec_13198 unpaid for sanitize); full materialized content write; flow_adaptation auto-confirm |
| Brittle predicates vs simple rules | **partial** | Dense listen-complete / hanging / same-speaker / Phase-A seated rules — mostly named policy, not mystery thrash |
| Disproportionate shard/memo/resume | **yes** | ~2k LOC; 7 hitch shards + QC; 24-stage inner walk; running/resume/listen_restage state machine |
| “Fix everything downstream” behavior | **yes** | Remap-all + VO reattach + omit stamp + hosted clamp + layup adopt + structure align + sanitize restamp + ranking unmark |

**Over-engineered?** `yes`  
**Scorecard verdict:** `FAIL`

### 5b — Re-score after S1–S5 (MODE=fix)

| Check | Answer | Delta | Evidence now |
|-------|--------|-------|--------------|
| Responsibilities count | **3** | 6→3 | Recut+boundaries · paid id remap · chapter authority (+ optional lattice/structure). Kitchen peeled; gate auto-confirm gone; walk skip when identity |
| Dual / competing SSOTs | **partial** | yes→partial | Boundaries still hitch-published (constitutional); no longer republishes ideal_cuts_materialized cuts |
| Soft-heal / thrash re-admit loops | **partial** | same | Lattice unmark / resume unchanged (by design) |
| Co-producer / unpaid land | **no** | yes→no | Remap preserves prior `producer_stage`; gap commit respects remap stages; no flow_adaptation write; hitch adopt skips gap republish |
| Brittle predicates vs simple rules | **partial** | same | Recut policy density unchanged |
| Disproportionate shard/memo/resume | **partial** | yes→partial | Full 24-stage order kept (safest); walk skipped only when no end/id churn (S4) |
| “Fix everything downstream” behavior | **no** | yes→no | No VO reattach / omit stamp / hosted clamp; layup adopt id-only without gap publish |

**Over-engineered?** `partial` — one hard fail-if (responsibilities=3) + residual dual/disproportionate partials.  
**Scorecard verdict:** `FAIL`

- Flip to PASS: peel ranking-lattice restamp out of hitch (or fold into remap-only), and/or treat chapter-authority as support of one “recut+bind” job so responsibilities ≤2 with no dual-SSOT yes.

---

## 6. Complexity subtraction list

| id | P | unambiguous\|needs_you | Status | Change | Clears check | Acceptance hint |
|----|---|------------------------|--------|--------|--------------|-----------------|
| S1 | P0 | unambiguous | done | omit hitch rewrite of `ideal_cuts_materialized` (SHARED remap only) | Dual SSOT / co-producer | no `hitch: true` cut corpus |
| S2 | P0 | unambiguous | done | preserve prior `producer_stage` on remap + gap `_resolve_gap_land_producer` for `SEGMENT_ID_REMAP_STAGES` | Co-producer unpaid | gap producer stays framing/layup |
| S3 | P1 | unambiguous | done | peel reattach/omit-stamp/clamp; hitch layup adopt skips gap publish | Fix-everything | `vo_gap.peeled=s3_no_gap_kitchen` |
| S4 | P1 | needs_you→safest | done | keep full restage list; skip inner walk only when no end change + identity/empty map | Disproportionate (partial) | `hitch_inner_walk_needed` |
| S5 | P2 | needs_you→safest | done | `_ensure_inner_walk_gates` no-op (no flow_adaptation write) | Co-producer | pickup stays unconfirmed |

Operator decisions: build S1–S5 safest; S4 = skip walk when remap-only (do not shrink list); S5 = no auto-confirm (no new refuse storm).

Also: heal allowlist `hitch_layup_adopt_failed` so HR-1 pin to layup is not clamped/refused.

---

## 7. Root-cause verdict

High-risk was hitch as mini-pipeline + unpaid co-producer. S1–S5 shipped safest peels: no materialized cut republish, paid land on remaps, no gap kitchen / gate forge, walk only when id/end churn. Residual FAIL is responsibilities=3 + constitutional boundary co-publish + 24-stage list retained by choice.

---

## 8. Recommended next action

`leave` / monitor — optional follow-up to get PASS: fold lattice restamp into remap path or count chapter-authority as part of bind job (responsibilities ≤2).

---

## 9. Scope fence

Upstream poison owner (if any): none required for hitch bloat — narrative_arc_plan is a legitimate prerequisite.  
Downstream victims (names only): `connector_fuse_pass_pre_ranking`, `full_master_ranking`, `gap_report_sanitize`, `refinement_agenda`, `nugget_layup_compose`, `edl_narrative_audit`.  
Did **not** redesign other stages (heal allowlist is hitch HR-1 support only).
