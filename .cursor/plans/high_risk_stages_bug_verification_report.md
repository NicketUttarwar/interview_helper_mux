# High-risk stages — post-simplify bug verification

**Date:** 2026-09-25  
**Scope:** All stages in `high_risk_error_stages_report.md` Audit findings (except `transcript_review` gate, still `not_started`).  
**Method:** HEAD code + ownership + stage contracts + simplify/harden/land-honesty pytest (not full-auto archaeology).  
**Fix pass:** `fix_verification_bugs_8749f0f5` Waves 1–4 landed. Locked defaults: no new pipeline stage (layup S6 deferred); dual-era gap body stays compose|layup (GFC S10 leave/monitor); GRS co-producers stay.

**Suite snapshot:** **370 passed / 0 failed** across simplify + harden + land-honesty pins (Wave 4 minimum plus related simplify/harden files). Wave 4 minimum from the plan: 288 passed / 0 failed.

---

## Executive verdict

Simplification held: stages stay **shape + refuse + honest done** and did not re-introduce kitchen heal loops.

The P0/P1 product bugs and contract/test drift from this report are **closed**:

1. Contract YAML peels now match the already-written simplify tests (CFP hard manifest, SOS/`llm_execute`, FMR soft trim, GFC/VO/process lifecycle).
2. Delivery footguns that could stall a run are fixed: VLA 0.0.0 stub, Clinic E `gap_unsanitary` navigate, EDL hollow `mark_done`, ENA blank-empty order, layup structural QC + floor escalate, hitch remap × sole-writer, compose persist seed peel.
3. Three **residual scorecard FAILs** remain as leave/monitor: `nugget_layup_compose` (S6), `gap_framing_compose` (S10), `chapter_close_hitch` (resp=3). **Bugs cleared; S6/S10/resp peel deferred.**

**Overall:** production logic is safer than the pre-fix HEAD. Remaining risk is **intentional leftover over-eng** (dual-era gap body, layup publish still inside compose, hitch still three jobs), not unfixed P0 delivery bugs.

---

## §Failures (pytest — classified)

| Test | Class | Status |
|------|-------|--------|
| `test_cfp_pre_ranking_s1_s5_simplify::test_s5_contract_manifest_is_hard` | Incomplete ship | **FIXED** — manifest is hard |
| `test_artifact_sanitize_selection::test_sos_contract_has_no_llm_execute` | Incomplete ship | **FIXED** — process lifecycle, no `llm_execute` |
| `test_fmr_hardening::test_fmr_s5_contract_soft_trimmed_to_build_input` | Contract drift | **FIXED** — soft trim + `ideal_cuts_selection_seed.json` |
| `test_ena_s1_s5_simplify::test_s2_repair_edl_narrative_selection_never_blank_drops` | Product footgun | **FIXED** — empty-order guard + non-blank fixture |
| `test_layup_s1_s5_simplify::test_s2_layup_skips_manifest_and_brief_writes` | Stale fixture | **FIXED** — schema-complete manifest + `content_brief.topics` objects |
| `test_land_honesty_comprehensive::…gap_report_sanitize…` (×3) | Design vs test drift | **FIXED** — fixtures use foreign producer (`edl`); framing/layup stay paid co-producers |

---

## Per-stage report

Legend: **Bug verdict** `CLEAN` | `RISKY` | `BUGS` — post-simplify correctness, not over-eng scorecard.

### T0

| Stage | Audit | Bug verdict | Does well | Does poorly / residual |
|-------|-------|-------------|-----------|------------------------|
| `missing_framing` | PASS | CLEAN | Batch-fill honesty; CAP→high_gap; responsibilities thin | Thin CAP seals starve compose; dead fill helpers remain |
| `gap_framing_compose` | FAIL (partial) | RISKY | Authority gate / no-op under layup; persist no longer seeds; SDP output peeled | Dual-era SSOT left as federated compose\|layup — **bugs cleared; S10 peel deferred** |
| `full_master_ranking` | PASS | CLEAN | Seal-once; primary-impact restore; sides peeled to sanitize | Contract YAML now matches S5/S6 (soft trim, no bridges/SDP/`order_reconcile` outputs) |
| `selection_order_sanitize` | PASS | CLEAN | Shape-only + lattice verify/refuse; meta preserves producer | `llm_execute` dropped; bridges producer remapped off FMR |
| `nugget_layup_compose` | FAIL | RISKY | S7–S10 peels; open-high/must-keep always errors; floor miss escalates (no rank-select rewrite); persist via `write_json` | S6 dual publish still inside compose; `_framing_floor_topup` stub-raises — **bugs cleared; S6 peel deferred** |
| `edl_narrative_audit` | PASS | CLEAN | Demote-or-refuse; prepare read-only; empty-order guard | Dead `allow_blank_drop` kwarg removed; selection writes use `edl_narrative_audit` |
| `edl` | PASS | CLEAN | Cut+refuse peel landed; S1–S5 simplify green | Soft `except: mark_done("edl")` removed; incompleteness re-raises |

### T1

| Stage | Audit | Bug verdict | Does well | Does poorly / residual |
|-------|-------|-------------|-----------|------------------------|
| `sound_design_plan` | PASS | CLEAN | Invent assets only; compose owns cues/slots | Placeholder helpers stub-raise (no silent re-wire) |
| `vo_line_adjudicate` | PASS | CLEAN | Advisory stamps; 0.0.0 + flag-off both persist skip stub | Synth is no longer seed-blocked on original brain |
| `vo_synthesize` | PASS | CLEAN | Admit→one render→seal; no EDL restamp | Soft seats/ledger claimed in contract; lifecycle is execute |
| `connector_fuse_pass_pre_ranking` | PASS | CLEAN | Dedicated rounds; HV/diar/lattice peeled | S5 hard `segments/manifest.json` landed |
| `selection_framing_apply` | PASS | CLEAN | Exclude commit + stamp seats | Clinic E: bare `gap_unsanitary` now allowlisted → `w1_sanitize_unsanitary` |
| `refinement_agenda` | PASS | CLEAN | Agenda-only; no gap/selection thrash | Seed-order heat downstream of layup |
| `gap_report_sanitize` | PASS | CLEAN | Shape+stamp; body rewrite peeled; Clinic E navigate matches | Co-producers stay (anti-thrash); land-honesty uses foreign producer |
| `chapter_close_hitch` | FAIL | RISKY | Unpaid land peeled; remap × sole-writer exempt via `mutation_class=segment_id_remap`; `vo_seed_seg_*` covered | Resp≈3 + 24-stage walk — **bugs cleared; resp peel deferred** |
| `transitions` | PASS | CLEAN | Demote under layup; incomplete glue refuses | Pair-freeze / deferred shards (monitor) |

### T2

| Stage | Audit | Bug verdict | Does well | Does poorly / residual |
|-------|-------|-------------|-----------|------------------------|
| `junction_snip_qa` | PASS | CLEAN | Repair + critical remaster seat; S6(B) paid land | Remaster mid-flight still blocks mix (intentional) |
| `mix` | PASS | CLEAN | Refuse unclean → render → seat | Realized-time EDL stamp residual (HAU, not dual SSOT) |
| `master_finalize` | PASS | CLEAN | Refuse→stamp; PMQ not re-eval’d here | Master.wav can exist while finalize still fails quality |
| `listen_delight_audit` | PASS | CLEAN | APPLY peeled; post_mix demoted; ownership pins | Remutate/seal fights if upstream rewrites under seal |
| `podcast_publish` | PASS | CLEAN | Refuse→assemble→stamp; no nested PMQ/transcript heal | Ship completion still fails on upstream PMQ |

### T3

| Stage | Audit | Bug verdict | Does well | Does poorly / residual |
|-------|-------|-------------|-----------|------------------------|
| `framing_posture_decide` | PASS | CLEAN | Advisory+stub; honest schema | Seed-order vs `content_context` noise |
| `vernacular_segment_sanitize` | PASS | CLEAN | Lexicon heal_pin→FMR; hollow refused | Manifest rematerialize shared bus (paid by design) |
| `mastering_shape_agenda` | PASS | CLEAN | Hollow OpenAI honest incomplete | Dual LLM cost when consumers unbound (policy) |
| `interview_spine_build` | PASS | CLEAN | Repairs-only; no transcript mutate | Authority friction cleared if S1–S4 hold |
| `transcript_review` | not_started | — | Operator G0 gate | Not in this pass |

---

## Footguns implemented (or left behind)

### P0 — closed this pass

1. **Audit/test greenwash on contracts** — **FIXED.** CFP hard manifest, SOS drop `llm_execute`, FMR soft trim / output peel landed + dependency data refreshed.
2. **VLA 0.0.0 never stubs** — **FIXED.** `persist_adjudication_skip_stub(..., skip_reason="homunculus_features_off")` before stamps/heal.
3. **ENA metadata-align dead kwarg** — **FIXED.** `allow_blank_drop=` dropped from `repair_master_selection`.
4. **ENA blank heuristic empties air order** — **FIXED.** Empty-order guard + non-blank S2 fixture.
5. **EDL hollow done** — **FIXED.** Soft `except: mark_done("edl")` removed.
6. **Layup aspirational softens structural QC** — **FIXED.** Open-high / must-keep stay errors under `layup_coverage_aspirational`.
7. **Clinic E navigate mismatch** — **FIXED.** Bare `gap_unsanitary` allowlisted to `w1_sanitize_unsanitary`.
8. **CFP `hard: []`** — **FIXED.** Manifest is hard.
9. **GRS hollow promote via co-producer allowlist** — **FIXED as designed.** Co-set kept; land-honesty fixtures use `edl` as foreign producer; paid framing/layup test added.
10. **Hitch remap × S9 sole-writer** — **FIXED.** `mutation_class=segment_id_remap` exempts id-map changes when texts match; S2 uses `vo_seed_seg_*`.
11. **Compose dual seed still in repair** — **FIXED.** Persist no longer seeds; HG-5 playbook remains the seed path.

### P1 — latent / confusing (mostly closed or accepted)

12. Layup S6 dual publish+floor still inside compose — **DEFERRED** (no new pipeline stage). Hollow preserve only when prior active ≥ need; else floor escalate.
13. Silent foreign-write skip (`run_context` S2) — **KEPT** (intentional); fixtures schema-complete so skip is reachable.
14. Dead `_framing_floor_topup` / hitch `reattach_vo_to_gap_report` / SDP placeholders / `_seed_missing_high_gap_interviewer_lines` — **FIXED.** Helpers stub-raise or return peeled no-op.
15. `GAP_REPORT_SOLE_BODY_WRITER` name vs dual pre-authority writers — **ACCEPTED** (compose\|layup federated).
16. **`_persist_gap_disk` / empty `stage_key` / GRS `fs_write_json` bypass** — **FIXED.** Persist via `write_json`; empty key refuses existing-body rewrite unless explicit `ops`/`fixture` role; `AuthorityDenied` is not swallowed.
17. Process stages advertising `llm_execute` — **FIXED.**
18. Seat-freeze no-ops that mark done when evidence is stale — monitor.

### P2 — monitor (unchanged)

19. Hitch responsibilities=3 + 24-stage walk on churn — **DEFERRED** (resp peel).
20. Junction paid remaster / mix unpaid (intentional).
21. Mix `_seat_after_mix` swallows seat exceptions; incomplete-cut soft-skip non-Loud.
22. T3 fixture debt (hm1 heuristic under LLM-on defaults; ISB skip SAP schema).
23. Layup hollow preserve under floor (not topup; only when already satisfying).

---

## Subagent batch map

| Batch | Agent | Headline |
|-------|-------|----------|
| A framing/selection | [Bug-verify T0 framing/selection](fbbd2fef-4d74-4fd3-9927-0305868fce09) | MF CLEAN; GFC RISKY; FMR+SOS contract BUGS → contracts landed |
| B layup/EDL | [Bug-verify T0 layup/EDL](0b6ce8de-3d06-431f-81c1-e7aaf5987e01) | Layup aspirational + ENA kwarg + EDL hollow done → fixed |
| C VO/SDP/fuse | [Bug-verify T1 VO/SDP/fuse](6e6b3394-6439-491a-a73a-62882870ff3a) | VLA 0.0.0 + CFP → fixed |
| D selection/refine | [Bug-verify T1 selection/refine](8b3da87e-1076-4c6e-87e0-8444bc14658f) | Clinic E navigate + hitch remap → fixed |
| E ship gates | [Bug-verify T2 ship gates](c5bf2428-1c40-43e1-94ce-4beed9d7c2fb) | All five CLEAN |
| F early T3 | [Bug-verify T3 early stages](0e0b46c6-bc69-434c-998d-6086985e2020) | All four CLEAN |
| G dual SSOT | [Deep-verify layup gap dual SSOT](af9b0e1c-0cb8-4e0b-9f50-34f298a1150f) | Remap exempt + persist seed peel + `write_json`; S6/S10 deferred |

---

## What the campaign did well (cross-cutting)

- **Refuse over soft-heal** on EDL body, mix, finalize, publish, VO render, transitions glue.
- **Body text sole writers** narrowed to compose\|layup; stamp stages guarded; remap id-maps exempt.
- **Selection sanitize** stopped re-admitting membership (shape + refuse).
- **Hitch / fuse / SFA / GRS** peels removed the worst unpaid kitchens.
- **T2/T3 ship + early stages** verify CLEAN after peels.
- **Contracts now match tests** instead of advertising peeled work that never landed.

---

## Recommended next actions (deferred / leave-monitor)

1. **S6** — peel publish+floor out of `nugget_layup_compose` into a dedicated seed (new pipeline stage; out of this pass).
2. **S10** — collapse dual-era gap body to a single forever writer, or keep federated compose\|layup and stop scoring it FAIL.
3. **Hitch resp** — fold lattice into remap / count bind as one job so responsibilities ≤ 2.
4. T3 hm1/ISB fixture debt if those stages are next.
5. `transcript_review` audit (not started).

---

## Scorecard leftover FAILs (over-eng, not bugs)

| Stage | Why still FAIL | Flip | This pass |
|-------|----------------|------|-----------|
| `nugget_layup_compose` | Publish+floor inside compose; dual plan/gap | Ship S6 peel | **Bugs cleared; S6 peel deferred** |
| `gap_framing_compose` | Dual-era body SSOT | Ship S10 or accept federated leave | **Bugs cleared; S10 peel deferred** |
| `chapter_close_hitch` | Responsibilities=3 | Fold lattice into remap / count bind as one job | **Bugs cleared; resp peel deferred** |

*End of verification report.*
