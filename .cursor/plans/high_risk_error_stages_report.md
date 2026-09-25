# High-risk / high-critical error stages — master report

## Stage picker (use these numbers)

Paste into a new Agent chat (replace the number):

```
/high-risk-audit STAGE=45
Follow .cursor/skills/high-risk-stage-audit/SKILL.md
```

One stage per line — `#` then name (same order as Quick index below):

```
45  nugget_layup_compose
41  selection_order_sanitize
30  missing_framing
32  gap_framing_compose
40  full_master_ranking
57  edl_narrative_audit
58  edl
53  sound_design_plan
55  vo_synthesize
54  vo_line_adjudicate
65  junction_snip_qa
64  mix
66  master_finalize
60  listen_delight_audit
39  connector_fuse_pass_pre_ranking
49  selection_framing_apply
47  refinement_agenda
46  gap_report_sanitize
38  chapter_close_hitch
52  transitions
72  podcast_publish
17  framing_posture_decide
19  vernacular_segment_sanitize
27  mastering_shape_agenda
7   interview_spine_build
—   transcript_review
```

---

**Purpose:** Single checklist of pipeline stages that most often **originate**, **amplify**, or **propagate** errors across full-auto runs that still ship `master/master.wav`. Use this file to pick `STAGE=` for `/high-risk-audit` (see Stage picker above).

**Corpus (primary):** 9 executions under `ASSETS/executions/` with `master/master.wav`:

| Run | Master size (approx) | Notes |
|---|---|---|
| `exec_13159_…20260918T235157Z` | 154M | early forensics |
| `exec_13161_…20260919T034356Z` | 188M | |
| `exec_13163_…20260920T034124Z` | 222M | |
| `exec_13165_…20260920T142408Z` | 199M | |
| `exec_13167_…20260921T044550Z` | 202M | end report exists |
| `exec_13170_…20260922T004948Z` | 163M | end report exists |
| `exec_13177_…20260923T001031Z` | 226M | end report exists |
| `exec_13183_…20260924T001619Z` | 214M | many iN clears |
| `exec_13198_…20260924T214444Z` | 256M | latest ship; 14 interventions |

**Evidence sources (per run):** `operator/forensics_errors.json|.md`, `operator/identical_failures.json`, `mastering/homunculus/identical_stage_errors.json`, `master/junction_snip_qa.json`, `master/failure_review.json`, `e2e_failure_brief.json`, forensics end reports / intervene logs.

**Stage numbering:** Pipeline order from `src/interview_mux/v2/config.py` — Analysis **#1–#35**, Delivery **#36–#72**. Gates (`transcript_review`, G-Framing, G1, G-Publish) are noted separately when they block progress.

**Risk legend**

| Tier | Meaning |
|---|---|
| **T0 — Source + cascade** | Errors born here routinely poison later stages / selection / VO / EDL |
| **T1 — High frequency blocker** | Hits most master-shipping runs; stalls or thrash until healed |
| **T2 — Quality / ship gate** | Often recoverable but blocks mix/finalize/publish or leaves audible defects |
| **T3 — Authority / order friction** | Frequent `AuthorityDenied` / seed-order noise; lower product harm when recovered |

---

## Quick index (automation walk order)

Walk **T0 → T1 → T2** first. Skip pure seed-order-only stages unless Automation still wants coverage.

| # | Stage | Tier | Runs hit (of 9) | Why high-risk |
|---|---|---|---|---|
| 45 | `nugget_layup_compose` | T0 | 9/9 | Hosted VO floor, CTA omit, selection thrash, gap_report unpaid land |
| 41 | `selection_order_sanitize` | T0 | 8/9 | Uncommitted pending, primary-impact restore, authority_undo oscillation |
| 30 | `missing_framing` | T0 | 6/9 | batch_fill incompleteness, budget door, propagates high_gap |
| 32 | `gap_framing_compose` | T0 | 8/9 | high_gap_unframed, spoken_copy_guard, freeze/authority thrash |
| 40 | `full_master_ranking` | T0 | 9/9 | never_exclude_primary_impact, freeze vs narrative/manifest |
| 57 | `edl_narrative_audit` | T0 | 9/9 | Chapter orphans, blank hard_keep drop → sanitize thrash |
| 58 | `edl` | T0 | 9/9 | Missing VO WAVs, opening_orientation, freeze ownership |
| 53 | `sound_design_plan` | T1 | 8/9 | Cue/slot validation storms; freeze vs soundscape/narrative |
| 55 | `vo_synthesize` | T1 | 8/9 | G1 / seed-order / budget; missing WAVs cascade into EDL |
| 54 | `vo_line_adjudicate` | T1 | 5/9 | Schema/hollow done; spoken scaffolding refusals |
| 65 | `junction_snip_qa` | T2 | 7/9 + all masters | Mid-word / silence / music cuts; blocks mix |
| 64 | `mix` | T2 | 8/9 | incomplete_cut_unresolved, mix_seat, delight freeze |
| 66 | `master_finalize` | T2 | 8/9 | post_master_quality / hollow mark_done |
| 60 | `listen_delight_audit` | T2 | (gate) | Authoritative ship gate; remutate loops |
| 39 | `connector_fuse_pass_pre_ranking` | T1 | 9/9 | Premature delivery complete; transcript authority |
| 49 | `selection_framing_apply` | T1 | 8/9 | Blocked on layup incomplete; selection thrash |
| 47 | `refinement_agenda` | T1 | 6/9 | Seed-order pile-up behind layup / ranking |
| 46 | `gap_report_sanitize` | T1 | 2/9 (severe when present) | Seed-order + gap ownership co-producer land |
| 38 | `chapter_close_hitch` | T1 | 3/9 | Ideal-cuts authority; id remap cascades |
| 52 | `transitions` | T1 | 6/9 | forensics_stall + phase_a_edl |
| 72 | `podcast_publish` | T2 | 9/9 | post_master_quality / S3 / escalate (after master exists) |
| 17 | `framing_posture_decide` | T3 | 9/9 | Seed-order vs `content_context` (homunculus) |
| 19 | `vernacular_segment_sanitize` | T3 | 9/9 | Same seed-order class |
| 27 | `mastering_shape_agenda` | T3 | 9/9 | Research routing prereq + hollow OpenAI agenda |
| 7 | `interview_spine_build` | T3 | 9/9 | Authority vs `transcribe` freeze |
| — | `transcript_review` (G0) | T3 | 9/9 | handle_gate (operator) |

---

## Cascade map (how errors spread)

```
missing_framing ──► gap_framing_compose ──► gap_report / hosted VO floor
        │                    │
        ▼                    ▼
full_master_ranking ◄── selection_order_sanitize ◄── framing_coverage / media_ip_cta
        │                    │
        ▼                    ▼
nugget_layup_compose ──► refinement / selection_framing_apply / air_contract
        │
        ▼
vo_line_adjudicate → vo_synthesize → edl_narrative_audit → edl
        │                                    │
        ▼                                    ▼
sound_design_plan ──────────────────► mix ← junction_snip_qa ← listen_delight
        │
        ▼
master_finalize → podcast_publish (quality escalate)
```

**Typical poison pattern:** bad framing/selection membership → layup cannot meet hosted VO floor → VO WAVs missing → EDL / narrative audit thrash → junction residuals → mix refuse → finalize quality fail (even when a master.wav eventually lands after heals).

---

## T0 — Source + cascade (review first)

### #45 — `nugget_layup_compose` (plan_rank / LLM)

**Risk:** Highest product + thrash risk across all 9 masters. Every e2e failure brief in this corpus points here (“pre-EDL delivery QC incomplete”).

**Common errors**

| Error / predicate | What happens | Propagates to |
|---|---|---|
| `hosted_vo_floor_unmet` / `hosted_vo_floor_unsatisfiable` | G-Framing Yes needs ≥N synthetic host lines; gap_report empty or thin | refinement, selection_framing_apply, VO contract ladder, EDL |
| `selection_cta_omit` / media_ip_cta thrash | Garbled/CTA scraps re-admitted then omitted; `selection_commit_refused` | selection_order_sanitize oscillation |
| LLM `partial` + `transcript_excerpt` needs | Hollow/garbled segment text; shard resume + attempt_memo refuse | driver restarts, unpaid land |
| `layup_coverage` / nugget air coverage below min | QC fail (e.g. 0.833 &lt; 0.85) | sound_design_plan / delivery premature |
| AuthorityDenied on `segments/manifest.json` | Freeze vs segment_classification | heal loops |
| `high_gap_unframed` under layup hollow-done | Done claimed while gaps unpaid | gap_report ownership / stage_completion |

**Automation review focus:** gap_report line count vs G-Framing; CTA/never_touch segments; shard memo; co-producer land stamps on `gap_report`.

---

### #41 — `selection_order_sanitize` (plan_rank)

**Risk:** Central thrash hub. Fixes and breaks membership for everyone downstream.

**Common errors**

| Error / predicate | What happens | Propagates to |
|---|---|---|
| `master/selection.json has newer uncommitted pending` | Sanitize refuses while pending write open | ranking / layup resume |
| `framing:primary impact … never_exclude_primary_impact` | Append restore / wrong insert order → mid_arc_reverse_jump | air_order integrity, edl_narrative |
| `authority_undo_thrash` / hash or action oscillation | sanitize ↔ ranking / edl_narrative_metadata_align | halt risk; unpaid land |
| `sanitize_refused: segment_starts_unavailable` | Cannot place restores | framing coverage incomplete |
| Restores media_ip_cta / never_touch primaries | Bad scrap back on-air | layup excerpt thrash |

**Automation review focus:** restore-by-tape-start vs append; never_touch + CTA skip; paid-land aliases (`selection`, `artifact_sanitize.selection`).

---

### #30 — `missing_framing` (gaps / LLM)

**Risk:** Early framing incompleteness that permanently shapes gap_report and ranking.

**Common errors**

| Error / predicate | What happens | Propagates to |
|---|---|---|
| `missing_framing batch_fill` — LLM must score remaining segs | Budget / dispatch_cap refusal; superseded fill duplicates block done | gap_framing_compose, high_gap |
| AuthorityDenied vs topology / boundaries / overlap repair | Freeze ownership fights | stalls |
| Thrash / forensics_stall | Repeated incomplete fills | delivery premature_complete |

**Automation review focus:** batch_fill incompleteness last-wins; budget door for unscored fills.

---

### #32 — `gap_framing_compose` (gaps / LLM)

**Risk:** Writes VO lines into gap_report; copy-guard and high-gap failures starve synthesis.

**Common errors**

| Error / predicate | What happens | Propagates to |
|---|---|---|
| `high_gap_unframed` + pre-flush “no interviewer line” | Soft heal refused; WriteApprovalBlocked | layup / ranking barriers |
| `spoken_copy_guard` (spoken_repeated_sentence, no_grounded_fallback) | Required VO blocked | vo_contract_ladder missing lines |
| Word-count post-commit (context_setup max 20) | Validation fail after commit | retries |
| `authority_undo_thrash` / freeze guard — refuse LLM fall-through | Stage stuck | gap_report pending_only |
| `gap_report.json is pending_only` | Consumers cannot read | refinement / sanitize |

**Automation review focus:** interviewer line presence on high-gap segs; copy-guard fallbacks; freeze evidence before LLM.

---

### #40 — `full_master_ranking` (plan_rank / LLM)

**Risk:** Selection membership authority; wrong excludes create unhealable primary-impact debt.

**Common errors**

| Error / predicate | What happens | Propagates to |
|---|---|---|
| `never_exclude_primary_impact` (pre-flush barrier) | Soft heal refused | sanitize restore thrash |
| Manifest segment missing from ordered ∪ excluded | Commit barrier | downstream incomplete selection |
| AuthorityDenied vs narrative_plan / manifest / gap_evaluations | Freeze fights | seed-order storms later |

**Automation review focus:** primary impact set vs excludes; manifest completeness before flush.

---

### #57 — `edl_narrative_audit` (build / LLM)

**Risk:** Post-VO narrative QC that rewrites selection metadata and fights sanitize.

**Common errors**

| Error / predicate | What happens | Propagates to |
|---|---|---|
| Chapter orphans / `chapter_continuity_broken` | Segments between chapters unassigned | repair ↔ sanitize thrash |
| Blank-drop of **hard_keep** segs | hard_keep_missing after “repair” | selection_order_sanitize, EDL order drift |
| AuthorityDenied on `narrative_plan.json` (owner=narrative_arc_plan) | Hard freeze | stalls |
| `edl_narrative:vo_g1` / vo_synthesize not seed-complete | Audit before WAVs exist | false blockers |

**Automation review focus:** never blank-drop hard_keeps; demote stale chapter blockers when membership filled; co-producer land for edl_narrative_*.

---

### #58 — `edl` (build)

**Risk:** Locks timeline; missing WAVs and publishability checks here are late and expensive.

**Common errors**

| Error / predicate | What happens | Propagates to |
|---|---|---|
| Gap VO lines missing WAV | EDL refuse | mix/assembly blocked |
| `opening_orientation_inaudible` | PublishabilityBlocked post_edl | remasters |
| Freeze vs nugget_layup_plan / episode_structure | AuthorityDenied | thrash |
| Speech clip order ≠ selection (`selection_edl_order_drift`) | Junction / mix refuse | junction_snip_qa remaster |

**Automation review focus:** all seated VO WAVs present; hard_keep short speech floors; rebuild EDL from selection (no ID-only stamp).

---

## T1 — High frequency blockers

### #53 — `sound_design_plan`

- **Hits:** 8/9 runs; very high ledger volume (`stage_error` storms).
- **Common:** cue `palette_bed_placeholder` / `theme_underscore` not in soundscape cue_slots; AuthorityDenied vs soundscape_policy / narrative_plan / episode_structure; seed-order “complete air_script_seams / nugget_layup first”.
- **Propagates:** edl_narrative_audit, mix seat, music epoch consumers.

### #55 — `vo_synthesize`

- **Hits:** 8/9.
- **Common:** seed-order (must complete `vo_line_adjudicate`); `vo_g1` / handle_gate; `budget_exhausted`; seated synthesize line missing WAV (feeds **vo_contract_ladder** on all 9 runs).
- **Propagates:** edl missing WAVs, narrative audit, delight.

### #54 — `vo_line_adjudicate`

- **Hits:** 5/9.
- **Common:** schema — `final_text: None`; hollow mark_done; spoken scaffolding / name attribution LoudStageFailure; bad `nugget_intro_compose` schema.
- **Propagates:** vo_synthesize incomplete → EDL.

### #39 — `connector_fuse_pass_pre_ranking`

- **Hits:** 9/9.
- **Common:** `delivery:premature_complete:stage:connector_fuse_pass_pre_ranking`; AuthorityDenied on transcripts/index (ops freeze); thrash_detected.
- **Propagates:** gap_report_sanitize / ranking seed-order backlog.

### #49 — `selection_framing_apply` · #47 — `refinement_agenda` · #46 — `gap_report_sanitize`

- **Pattern:** Large seed-order pile-ups waiting on `#45 nugget_layup_compose` (and hitch / fuse / ranking). When layup is broken, these stages spam recoveries and look “hot” in ledgers even when they are not the root cause.
- **Real root often:** unpaid/incomplete layup or gap_report — review those first, then re-check these.

### #38 — `chapter_close_hitch`

- **Common:** AuthorityDenied mutating `ideal_cuts_materialized.json`; id remap side effects.
- **Propagates:** refinement / gap_report_sanitize seed-order; chapter membership for narrative audit.

### #52 — `transitions`

- **Common:** `forensics_stall`, `phase_a_edl` coupling.
- **Propagates:** edl_narrative hard_freeze on transitions.json.

---

## T2 — Quality / ship gates (audible + finalize)

### #65 — `junction_snip_qa`

Present on **all 9** masters (findings per run: ~10–55). Dominant finding kinds across corpus:

| Finding kind | Approx count (all masters) |
|---|---|
| `music_hard_transition` | ~104 |
| `mid_word_end` | ~93 |
| `trailing_silence` | ~89 |
| `mid_word_start` | ~10 |
| `leading_silence` / `incomplete_clause` | low |

**Ledger errors:** `incomplete_cut_unresolved`, `selection_edl_order_drift`, AuthorityDenied vs listen_delight under edl_sealed.

**Propagates:** `#64 mix` refuses live incomplete-cut residuals; `#66 master_finalize` post_master_quality (`no_critical_junction_residuals`); failure_review `junction_quality`.

### #64 — `mix`

- **Common:** `incomplete_cut_unresolved`; `mix_seat`; AuthorityDenied vs listen_delight_audit (mix_seated); seed-order (layup / delight incomplete).
- **Propagates:** finalize / publish escalate.

### #66 — `master_finalize`

- **Common:** LoudStageFailure post-master quality; hollow mark_done; finalize_inputs.
- **Note:** Master.wav can exist while finalize still fights quality — review junction residuals + delight before blaming finalize itself.

### #60 — `listen_delight_audit`

- Authoritative ship gate (scores in corpus typically ~0.95–0.98 `post_master`).
- Risk is **remutate / escalate loops** and freeze ownership when junction or mix try to rewrite under seal — not low delight scores on these 9 ships.

### #72 — `podcast_publish`

- **Common after master exists:** `HARD: post_master_quality unrecovered`, forensics_escalate, s3_sync consent, stack_shutdown.
- Lower “source” risk for tape errors; high for **ship completion**.

---

## T3 — Frequent but usually recovered (optional Automation)

| # | Stage | Typical error |
|---|---|---|
| 17 | `framing_posture_decide` | seed-order: complete `content_context` first |
| 19 | `vernacular_segment_sanitize` | same vs `content_context` |
| 27 | `mastering_shape_agenda` | seed-order vs research_routing; hollow/invalid OpenAI agenda |
| 7 | `interview_spine_build` | AuthorityDenied persist transcript vs `transcribe` freeze |
| — | `transcript_review` (G0 gate) | handle_gate — operator must clear STT |
| — | `split_plan_apply` (helper) | AuthorityDenied boundaries vs `edl_overlap_repair` |
| 21 | `connector_fuse_pass` | AuthorityDenied transcripts/index |
| 61–63 | `music_palette_compose` / `sfx_prompt_craft` / `mmaudio_sfx` | music_epoch / soundscape freeze (lower rate) |

---

## Cross-cutting error classes (not a single stage)

These show up as `failed_stage` / recovery labels and **feel** like stage bugs but are systemic:

| Class | Seen as | Meaning |
|---|---|---|
| `vo_contract_ladder` | recovery on all 9 runs | Seated VO line missing from gap_report or missing WAV |
| `delivery:premature_complete:*` | delivery pseudo-stage | Homunculus tried to finish phase early (phase_a_edl, vo_g1, mix_seat, named stage) |
| `seed_order_prereq` | many stages | Agenda raced ahead of prerequisites (often downstream of a real T0 failure) |
| `authority_denied` / freeze | ranking, SDP, EDL, hitch | Ownership SSOT — wrong writer under freeze |
| `authority_undo_thrash` / hash_oscillation | selection / gap_report | Two writers undoing each other |

---

## Per-run intervene hotspots (latest campaign)

From `.cursor/plans/full_auto_forensics_state.md` on **exec_13198** (14 interventions) — confirms T0 list:

1. `missing_framing` (budget + batch_fill) — i1, i2  
2. `selection_order_sanitize` / framing restore — i3, i8, i13  
3. `nugget_layup_compose` (memo, CTA, thrash, high_gap, unpaid land) — i4–i9  
4. `edl_narrative_audit` / `edl` / hard_keep blank-drop — i10–i12  
5. `vo_speech_qa` / mix unpaid land performance — i14  

Earlier end reports (`exec_13167`, `13170`, `13177`) show the same spine: layup ↔ sanitize ↔ VO ↔ junction ↔ mix.

---

## Automation review checklist (later)

For each T0/T1 stage above:

1. Open one recent master run (prefer `exec_13198`) and the stage’s primary artifacts.
2. Confirm whether the stage is **root** or **downstream of seed-order / unpaid land**.
3. Note the top 2–3 predicates from this report still present on disk.
4. Mark: **still broken / healed by code / needs product policy**.
5. Only then open older masters to see if the class is historical.

**Suggested walk order:**  
`#30 missing_framing` → `#32 gap_framing_compose` → `#40 full_master_ranking` → `#41 selection_order_sanitize` → `#45 nugget_layup_compose` → `#54–55 VO` → `#57–58 EDL` → `#65 junction` → `#64 mix` → `#66 finalize`.

---

## Method notes

- Stages with high ledger counts but mostly `seed_order_prereq` are ranked **T1/T3**, not T0, unless they also own product predicates (e.g. SDP cue validation).
- Gates and helper writers (`transcript_review`, `split_plan_apply`, `vo_contract_ladder`) are included when they dominate identical-failure traffic.
- This report is **observational** from shipped masters; it is not a predicate-family ledger mapping (per forensics campaign rules).

*Generated for Automation walkthrough prep — corpus date span 2026-09-18 → 2026-09-24.*

<!-- high-risk-audit-findings:start -->

## Audit findings (merged 2026-09-25T15:50:46Z)

Per-stage details live under `.cursor/plans/high_risk_stage_audits/`. Paste `/high-risk-audit STAGE=___` (see `.cursor/skills/high-risk-stage-audit/SKILL.md`); agents update their own row here when complete.

| Stage | Tier | Status | Over-eng? | Verdict / next | File |
|-------|------|--------|-----------|----------------|------|
| `nugget_layup_compose` | T0 | `complete` | yes | Dual SSOT + floor/CTA heals in one stage → `simplify` (peel publish/floor; forbid manifest writes) | [nugget_layup_compose.md](high_risk_stage_audits/nugget_layup_compose.md) |
| `selection_order_sanitize` | T0 | `not_started` | — | — | [selection_order_sanitize.md](high_risk_stage_audits/selection_order_sanitize.md) |
| `missing_framing` | T0 | `not_started` | — | — | [missing_framing.md](high_risk_stage_audits/missing_framing.md) |
| `gap_framing_compose` | T0 | `not_started` | — | — | [gap_framing_compose.md](high_risk_stage_audits/gap_framing_compose.md) |
| `full_master_ranking` | T0 | `not_started` | — | — | [full_master_ranking.md](high_risk_stage_audits/full_master_ranking.md) |
| `edl_narrative_audit` | T0 | `not_started` | — | — | [edl_narrative_audit.md](high_risk_stage_audits/edl_narrative_audit.md) |
| `edl` | T0 | `not_started` | — | — | [edl.md](high_risk_stage_audits/edl.md) |
| `sound_design_plan` | T1 | `not_started` | — | — | [sound_design_plan.md](high_risk_stage_audits/sound_design_plan.md) |
| `vo_synthesize` | T1 | `not_started` | — | — | [vo_synthesize.md](high_risk_stage_audits/vo_synthesize.md) |
| `vo_line_adjudicate` | T1 | `not_started` | — | — | [vo_line_adjudicate.md](high_risk_stage_audits/vo_line_adjudicate.md) |
| `junction_snip_qa` | T2 | `not_started` | — | — | [junction_snip_qa.md](high_risk_stage_audits/junction_snip_qa.md) |
| `mix` | T2 | `not_started` | — | — | [mix.md](high_risk_stage_audits/mix.md) |
| `master_finalize` | T2 | `not_started` | — | — | [master_finalize.md](high_risk_stage_audits/master_finalize.md) |
| `listen_delight_audit` | T2 | `not_started` | — | — | [listen_delight_audit.md](high_risk_stage_audits/listen_delight_audit.md) |
| `connector_fuse_pass_pre_ranking` | T1 | `not_started` | — | — | [connector_fuse_pass_pre_ranking.md](high_risk_stage_audits/connector_fuse_pass_pre_ranking.md) |
| `selection_framing_apply` | T1 | `not_started` | — | — | [selection_framing_apply.md](high_risk_stage_audits/selection_framing_apply.md) |
| `refinement_agenda` | T1 | `not_started` | — | — | [refinement_agenda.md](high_risk_stage_audits/refinement_agenda.md) |
| `gap_report_sanitize` | T1 | `not_started` | — | — | [gap_report_sanitize.md](high_risk_stage_audits/gap_report_sanitize.md) |
| `chapter_close_hitch` | T1 | `not_started` | — | — | [chapter_close_hitch.md](high_risk_stage_audits/chapter_close_hitch.md) |
| `transitions` | T1 | `not_started` | — | — | [transitions.md](high_risk_stage_audits/transitions.md) |
| `podcast_publish` | T2 | `not_started` | — | — | [podcast_publish.md](high_risk_stage_audits/podcast_publish.md) |
| `framing_posture_decide` | T3 | `not_started` | — | — | [framing_posture_decide.md](high_risk_stage_audits/framing_posture_decide.md) |
| `vernacular_segment_sanitize` | T3 | `not_started` | — | — | [vernacular_segment_sanitize.md](high_risk_stage_audits/vernacular_segment_sanitize.md) |
| `mastering_shape_agenda` | T3 | `not_started` | — | — | [mastering_shape_agenda.md](high_risk_stage_audits/mastering_shape_agenda.md) |
| `interview_spine_build` | T3 | `not_started` | — | — | [interview_spine_build.md](high_risk_stage_audits/interview_spine_build.md) |
| `transcript_review` | T3 | `not_started` | — | — | [transcript_review.md](high_risk_stage_audits/transcript_review.md) |

<!-- high-risk-audit-findings:end -->
