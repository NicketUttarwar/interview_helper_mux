# Full-auto forensics — root causes by execution

**Purpose:** Identify, for each shipped forensics campaign, the **true origin stages** where defects started, separate from the stages that only **echoed** those defects, and explain **why** each root happened.

**Input tape (all campaigns below):** `mohan_uttarwar_podcast_transforming_cancer_science_direct.mp3`  
**Mode:** Full-auto forensics (`MUX_FRESH=1` once per campaign; continue same `run_id` after each patch).

**How to read this report**

| Question | Meaning |
|----------|---------|
| **Where did the error message appear?** | Symptom / detector stage (often `edl`, `transitions`, `refinement_agenda`, `mix`, `podcast_publish`). |
| **Where did the defect start?** | Origin / producer stage — the place a product fix must land. |

Patching a symptom stage without fixing the origin does not cure the thrash. Intervene IDs (`iN`) **reset per campaign** — `i9` on exec_13159 is not the same bug as `i9` on exec_13177.

**Primary sources**

- End reports: `full_auto_forensics_end_report.md`, `…_exec_13167.md`, `…_exec_13170.md`, `…_exec_13177.md`
- Live state / intervenes: `full_auto_forensics_state.md` (currently exec_13177)
- Deep dive: `full_auto_forensics_error_analysis_exec_13177.md`
- Raw ledgers: `ASSETS/executions/exec_131{59,67,70,77}_*/operator/forensics_errors.md`
- Cascade fixtures: `tests/test_i*_*.py` under `MUX_FORENSICS=0`

**Campaigns covered in depth**

| Exec | Window | Interventions | Ledger size | Ship |
|------|--------|---------------|-------------|------|
| **13159** | 2026-09-18 → 19 | i1–i9 (+i5b, i6c/d) | ~722 entries / 92 uniq | yes (local) |
| **13167** | 2026-09-21 | i1–i11h (15) | ~1010 / 73 uniq | yes |
| **13170** | 2026-09-22 | i1–i8 (+i7b–j) | ~208 | yes |
| **13177** | 2026-09-23 | i1–i15 (+i12b, i14b) | 476 / 97 uniq | yes |
| **11871** (archive) | 2026-09-16 | i1–i54 | huge (ownership era) | yes |

Sibling HINT / partial runs (13161, 13163, 13165, 13168, …) are summarized at the end; they are not full intervene-logged campaigns.

---

## Executive cross-cut: recurring origin families

These patterns recur across campaigns. The **surface stage** changes; the **origin class** does not.

| Origin family | What actually breaks | Typical echo stages | Seen in |
|---------------|----------------------|---------------------|---------|
| **Layup / hosted VO floor** | CTA omit, hollow scrub, or incomplete layup leaves &lt; `min_synthetic_vo_lines` active host lines | `refinement_agenda`, `air_contract_sanitize`, `transitions`, early `edl` / G1 | 13159, 13167, 13170, 13177 |
| **VO authority after WAV exists** | Contract/omit/StageInfo/bind treat seated audio as failed or purge it | `vo_synthesize`, `assembly_preview`, `edl`, VO ladder | 13170, **13177** (dominant) |
| **SDP honesty vs freeze** | Dens wipe, off-selection beds, silent skip-write, invent refuse under mix_seated | `sound_design_plan`, `music_palette_compose` | **13167**, 13170, **13177** |
| **mix ⇄ junction seat** | `precedes_mix` / stale assembly / resume always→mix / hollow mark_done | `mix`, `junction_snip_qa`, `premature_complete:mix_seat` | **13159**, **13167** |
| **Hollow mark_done** | `mark_done` before artifact sealed, seated, or PMQ present | adjudicate, mix, `master_finalize` | **13167** |
| **Premature pin / lease / sticky** | Driver resumes sealed or wrong stage; automation treats pin as success | delivery premature storms, idle spin | 13159, **13170**, 13167 |
| **Hard-freeze / End-A ownership** | Persist without ALLOW or End-A reason → deny or silent no-op | `edl_narrative_audit`, SDP duration | 13167, 13170, HINT siblings |
| **Ownership ALLOW / StageInfo flush** | Uncataloged path or undeclared staged output dropped | ship / QC / publish noise | **11871**, 13159 i9, 13177 i12 |

---

# 1. exec_13159 — seat / remaster / ownership gates

**run_id:** `exec_13159_d19c15b58ab4_20260918T235157Z`  
**Outcome:** Local ship. Delight ~0.9547. S3 deferred on G-Publish consent.  
**Dominant HINT family (sibling digest):** `PIN_PREMATURE`.

### Campaign-defining origin stages

| Origin stage | Why it is a root | Loud echoes |
|--------------|------------------|-------------|
| **`nugget_layup_compose`** (+ adopt path) | Wrong `stage_key` on adopt (`edl` DENY) left selection/plan drifted; freeze-sticky heal re-invoked LLM under seal | `mix` seed-order, junction clip-count thrash |
| **`junction_snip_qa` remaster path** | Critical residuals mislabeled budget exhaust; remaster dropped mix QC / ship-bar defects | `mix` incomplete_cut; `podcast_publish` / PMQ spam |
| **`junction_recut_precedes_mix` gate** | Deadlock: mix needs recut, junction needs `assembly.wav` only mix mints | mix ↔ junction ping-pong |
| **Ownership / delivery gates** | MSA `$ref`, boundary ALLOW gaps, hollow EDL without narrative audit, matrix version mismatch | early delivery “premature” / `authority_denied` noise |

### Root causes (intervention detail)

#### i1 — MSA `$ref` schema (origin: `mastering_shape_agenda`)

- **Surface:** Shape agenda / OpenAI structured output hollow or invalid; walk looked premature into delivery.
- **Why:** Structured-output schemas with `$ref` failed the MSA cutover → shape incomplete → downstream “analysis incomplete.”
- **Echo:** `delivery_brief_build`, `premature_complete:phase_a_edl`.
- **Fix class:** Schema / MSA cutover (prior-session band with i2–i4).

#### i2 — Layup wordcap (origin: `nugget_layup_compose`)

- **Surface:** Layup word-budget / compose fail.
- **Why:** Wordcap validation stopped a complete layup → hosted floor / selection starvation.
- **Echo:** seed-order to mix/refinement; `hosted_vo_floor_unmet` volume.

#### i3 — Boundaries ownership (origin: `artifact_ownership`)

- **Surface:** `authority_denied` on boundary enrich.
- **Why:** Fail-closed catalog lacked ALLOW for legitimate `boundary_enrich` writes.
- **Echo:** `split_plan_apply` / connector_fuse persist denials.

#### i4 — CAP-seal / hitch under freeze (origin: CAP-seal / hitch path)

- **Surface:** CAP seal / hitch break; `segment_id_remap` friction.
- **Why:** Fabricated CAP seal under freeze broke hitch remap constitution.
- **Echo:** junction / selection drift.

#### i5 — Hollow EDL without narrative audit (origin: delivery gate / EDL acceptance)

- **Surface:** EDL could progress without `edl_narrative_audit`.
- **Why:** Missing producer gate let hollow EDL forward into mix/junction.
- **Echo:** mix/junction consuming unsanitary EDL.
- **Fix:** Require audit before EDL done.

#### i5b — Ownership matrix mismatch (origin: forensics restamp)

- **Surface:** False `authority_denied` after ALLOW patches.
- **Why:** Live run’s stamped matrix version lagged code → denials that looked like product bugs.
- **Echo:** cascading ownership noise.
- **Fix:** Restamp matrix so same `run_id` can continue.

#### i6 — Sealed layup adopt wrong `stage_key` (origin: `assembly.adopt_layup_plan_to_selection`)

- **Surface:** `complete nugget_layup_compose before mix`; plan length ≠ selection length.
- **Why:** Adopt used DENY stage_key `edl` → silent `AuthorityDenied` → stale plan ids survived; heal wanted to re-run layup under `edl_sealed`.
- **Echo:** mix, junction (transient clip-count mismatch), dangerous LLM recompose under seal.
- **Fix:** Adopt as `nugget_layup_compose`; driver adopts then resumes consumer.
- **Test:** `test_edl_adopt_must_use_layup_owner_not_edl_stage_key`.

#### i6c/d — Freeze-sticky rewind (origin: driver seed-heal)

- **Surface:** Post-EDL seed-order rewind to nugget/SDP; LLM re-run under freeze.
- **Why:** Heal unmarked sticky producers as hollow and re-invoked them under seal.
- **Echo:** mix seed-order storms.
- **Fix:** `FREEZE_STICKY_SEED_STAGES` includes layup+SDP; refuse unmark; seal sticky + resume consumer.

#### i7 — Critical remaster mislabeled budget exhaust (origin: `junction_snip_qa`)

- **Surface:** Remaster “budget exhausted” while incomplete_cut criticals remain.
- **Why:** Critical residuals took `path=repair` with `used=0` logged as budget exhaust instead of incomplete-clause retry.
- **Echo:** mix blocked on incomplete_clause (e.g. seg_018/031/035).
- **Test:** `test_jsq_critical_remaster_path`.

#### i8 — mix⇄junction `assembly.wav` deadlock (origin: `junction_recut_precedes_mix`)

- **Surface:** mix `assembly_not_rendered_from_current_edl`; junction missing `assembly.wav`.
- **Why:** Gates disagreed — mix needed junction recut; junction required assembly that only mix mints when `precedes_mix` was false (no live criticals).
- **Echo:** mix ↔ junction ping-pong; “run mix first” while mix cannot render.
- **Fix:** `precedes_mix` also when assembly missing/stale vs live EDL.
- **Test:** `test_junction_does_not_precede_when_assembly_missing` + `test_junction_precedes_when_existing_assembly_is_stale` (+ i25 cousins).

#### i9 — Junction remaster drops mix QC (origin: `junction_snip_qa.remaster_mix_only`)

- **Surface:** PMQ `planned_music_preserved` / `episode_close_outro_present`; ship-bar defects on done stages.
- **Why:** Remaster wrote `music_cue_coverage` under junction pending; StageInfo did not claim paths → flush dropped; stale ship-bar defects on already-done stages blocked PMQ honesty.
- **Echo:** `podcast_publish` / listen_delight ship-bar spam.
- **Fix:** Promote mix QC side-effects; mix owns coverage; reconcile defects for done stages.
- **Test:** `tests/test_i9_junction_remaster_promotes_mix_qc.py`.

### 13159 bottom line

True roots clustered in **layup adopt / sticky heal**, **junction remaster + precedes_mix**, and **ownership/gate honesty**. Loud `podcast_publish` and phase-A EDL noise were mostly echoes.

---

# 2. exec_13167 — SDP dens wipe + hollow mark_done + mix seat chain

**run_id:** `exec_13167_d19c15b58ab4_20260921T044550Z`  
**Outcome:** Local ship. Delight ~0.9654.  
**Ledger signal:** `sound_design_plan` alone ~662 hits — campaign dominated by **SDP cue_slots** thrash, then late **mix seat** chain.

### Campaign-defining origin stages

| Origin stage | Why it is a root | Loud echoes |
|--------------|------------------|-------------|
| **`sound_design_plan` / `soundscape_policy.refresh_cue_slots`** | Dens scorer wiped planned beds beyond max_beds; refresh ownership wrong | Massive SDP ledger storm |
| **`vo_line_adjudicate` / intro / spoken lint** | Hollow mid-batch mark_done; intro envelope unwrap; gendered pronoun | VO ladder / synthesize refuse |
| **`mix` + resume helpers** | Hollow mark_done (mtime), assembly_stale pin→junction, ledger sha ≠ final, remaster staging, premature_complete:mix_seat | junction thrash, delivery stuck on mix |
| **`master_finalize` / PMQ** | Delight loud-fail skipped PMQ persist | hollow finalize |
| **`nugget_layup_compose` (early)** | Hollow scrub dropped floor lines; DELIVERY_ORDER UnboundLocal | VO floor + walk crash |
| **`spoken_copy_guard` / remutate** | Mid-sentence fallback as bridge | `edl_narrative_audit` continuity |

### Root causes (intervention detail)

#### i1 — Hosted VO floor + UnboundLocal (origin: `nugget_layup_compose`)

- **Surface:** `hosted_vo_floor_unmet`; `DELIVERY_ORDER` UnboundLocalError.
- **Why:** Hollow scrub dropped foreign keep-on-air lines below floor; nested import crashed the walk.
- **Echo:** ranking continue; VO ladder.
- **Tests:** `test_hollow_preserve_retains_foreign_to_hold_vo_floor`, `test_run_until_done_no_nested_delivery_order_import`.

#### i2 — Interrupt / premature_cap ranking↔TCA (origin: `full_master_ranking` / premature_cap)

- **Surface:** Smart-resume→edl; sticky interrupt; ranking↔TCA idle spin.
- **Why:** Interrupt resume jumped past pending selection; premature_cap cycled ranking and TCA.
- **Fix:** Stay on ranking when selection pending; clear sticky interrupt.
- **Tests:** interrupt smart-resume + premature_cap ranking tests.

#### i3 — SDP cue_slots thrash (**campaign dominant**) (origin: `soundscape_policy` / SDP repair)

- **Surface:** Post-commit cue_slots / theme_underscore thrash (heal validate pass ↔ stage fail).
- **Why:** Dens scorer wiped planned `under_segment` beds beyond `max_beds`; refresh wrote without correct `stage_key`; inject failed when refresh threw.
- **Echo:** ~655 SDP-family ledger hits.
- **Fix:** Refresh with `stage_key=soundscape_policy_build`; merge planned beds beyond dens cap; isolate refresh failure.
- **Tests:** `test_score_cue_slots_preserves_planned_sdp_beds_beyond_dens_cap`, `test_sdp_bed_cue_slot_injections_survive_sound_design_plan_flush`.

#### i4 — Hollow mark_done mid adjudicate batch (origin: `vo_line_adjudicate`)

- **Surface:** `authority_denied:mark_done:hollow:vo_line_adjudicate` after LLM batch.
- **Why:** Each batch used `auto_complete=True` before `adjudication.json` sealed.
- **Fix:** `auto_complete=False` per batch; mark_done only after seal.
- **Test:** `test_run_adjudicate_batches_does_not_mark_done_mid_batch`.

#### i5 — Intro schema unwrap (origin: `nugget_intro_compose.persist_intro`)

- **Surface:** Intro JSON missing text/nugget_ids.
- **Why:** Persisted envelope without unwrapping `artifacts.stage_output`.
- **Echo:** adjudicate / synth.
- **Test:** `test_nugget_intro_compose_unwraps_stage_output_envelope`.

#### i6 — Gendered pronoun lint (origin: intro mint / `spoken_meta_lint`)

- **Surface:** Synthesize VO incomprehensible — `spoken_gendered_pronoun`.
- **Why:** Intro minted he/she without scrub.
- **Test:** `test_scrub_spoken_gendered_pronoun_clears_intro_preface`.

#### i7 — Budget epoch / lease / vo_g1 (origin: homunculus budget + walk + intro LimitExhausted)

- **Surface:** max_invokes refuse advances past incomplete VO; orphan pending_only; ESR lease; vo_g1 wavs=0.
- **Why:** Pre-patch attempt counts blocked post-patch work; walk advanced past incomplete critical; intro LimitExhausted didn’t reuse sealed; pending not flushed on fail.
- **Tests:** budget_epoch, walk refuse incomplete critical, intro reuse sealed.

#### i8 — ESR vo_wavs pin leapfrog (origin: `execution_status` pin matcher)

- **Surface:** ESR wait `fresh:vo_wavs` on done `sound_design_vo_finalize`; leapfrog to `master_transcript_build`.
- **Why:** Substring match treated `sound_design*` as VO; advanced ship-after-master without master.
- **Test:** `test_sound_design_vo_finalize_pin_ignores_vo_wav_freshness`.

#### i9 — Narrative plan hard_freeze ALLOW (origin: ownership + `align_narrative_plan_to_selection`)

- **Surface:** `authority_denied:persist:master/narrative_plan.json:edl_narrative_audit:hard_freeze`.
- **Why:** Audit needed metadata align under hard freeze but lacked ALLOW / mutation_class.
- **Test:** `test_edl_narrative_audit_may_align_narrative_plan_under_hard_freeze`.

#### i10 — Mid-sentence transition fallback (origin: `spoken_copy_guard` + remutate)

- **Surface:** `selected_continuity_broken` — fallback “alone does not settle…”.
- **Why:** Mid-sentence fallback accepted as bridge; remutate short-circuited on metadata-only notes.
- **Test:** `tests/test_i10_mid_sentence_transition_repair.py`.

#### i11 — Hollow mark_done:mix (mtime) (origin: `sound_design.mix`)

- **Surface:** `authority_denied:mark_done:hollow:mix` after successful render.
- **Why:** EDL write left assembly mtime older than EDL → seated check failed at mark_done.
- **Fix:** `ensure_assembly_mtime_seats_edl` before mark_done.
- **Test:** `tests/test_i11_mix_mark_done_seats_mtime.py`.

#### i11b–i11g — assembly_stale / remaster / resume chain (origin: resume + remaster helpers)

| Sub | Surface | Origin mechanism |
|-----|---------|------------------|
| **i11b** | cannot run junction: assembly_stale | `resolve_assembly_stale_resume` pinned junction instead of mix |
| **i11c** | premature_cap→junction while stale | `path_to_master_pin` preferred junction over mix |
| **i11d** | ledger sha ≠ final assembly | `write_render_ledger` fingerprinted pending not final_path |
| **i11e** | remaster under junction pending | nested mix lacked mix staging; mix self-blocked on assembly_stale |
| **i11f** | pre_mix incomplete_cut ← commitment diverge | remaster-only seam reasons misclassified as incomplete_cut |
| **i11g** | premature_complete:mix_seat after seated mix | resume always returned mix after music epoch |

**Tests:** `test_i11_assembly_stale_resume_pins_mix_not_junction`, `test_i11_path_to_master_pins_mix_when_assembly_stale`, `test_i11_write_render_ledger_fingerprints_final_not_pending`, `test_i11_remaster_mix_only_uses_nested_mix_staging`, `test_i11_premix_commitment_diverge_not_incomplete_cut`, `test_i11_advance_past_seated_mix`.

#### i11h — Hollow finalize / PMQ missing (origin: `run_post_master_quality`)

- **Surface:** `authority_denied:mark_done:hollow:master_finalize` (master present, PMQ missing).
- **Why:** Delight loud-fail aborted before PMQ persist; exception skipped pending flush.
- **Test:** `tests/test_i11_pmq_persists_when_delight_fails.py`.

### 13167 bottom line

**#1 root by volume:** SDP dens / cue_slots honesty (`sound_design_plan`).  
**#2 root by ship risk:** mix seat / hollow mark_done / resume chain.  
Early layup floor and mid-sentence transitions were real but smaller.

---

# 3. exec_13170 — VO walk honesty + speech-first music

**run_id:** `exec_13170_d19c15b58ab4_20260922T004948Z`  
**Outcome:** Local ship. Delight ~0.9502. Master ~29.6 min.  
**Interventions:** 16 (i1–i8 including i7 speech-first chain).

### Campaign-defining origin stages

| Origin stage | Why it is a root | Loud echoes |
|--------------|------------------|-------------|
| **`vo_contract` / omit / high-gap** | Waive/omit left flags and high gaps inconsistent | VO ladder, vo_g1 wavs=0 |
| **Agenda sticky + remutate + lease** | Sealed SDP sticky; remutate yanked past G1; sealed VO held expensive lease | premature_complete:phase_a_edl, skipped adjudicate |
| **`web/runner` premature_cap** | Automation got `ok:False` pin treated as success → idle spin | sound_design_vo_finalize idle |
| **HAU speech-first walk** | Music refused correctly on preview-only assembly, but walk/ESR/MUST_PRECEDE kept yanking | hollow Finished `music_palette`, mix thrash |
| **SDP duration under hard VO freeze** | Bare stage_key write silently no-op’d | sfx→mmaudio→junction duration band |

### Root causes (intervention detail)

#### i1 — HC-3 pending overlay invent (origin: `selection_order_sanitize` / write_mirrored)

- **Surface:** `uncommitted_pending_reason` — selection has newer uncommitted pending.
- **Why:** Mirrored write invented a pending twin → false incompleteness.
- **Test:** `test_hc3_pending_overlay`.

#### i2 — Omit-wins `execution_contract_waive` (origin: `vo_contract`)

- **Surface:** Omitted line lacks skip/omit flags.
- **Why:** Tier-D waive cleared flags but not durable omit-wins markers → ladder thrash.
- **Test:** `test_execution_contract_waive_survives_hosted_floor`.

#### i3 — High-gap omit demote (origin: omit repair + `clamp_resume`)

- **Surface:** `high_gap_unframed` + vo_g1 wavs=0.
- **Why:** Repair omit removed last high-gap cover without demoting gap; clamp skipped compose.
- **Test:** `tests/test_i3_omit_demote_high_gap.py`.

#### i4 — Sticky sealed SDP + remutate vs G1 (origin: agenda sticky + `delivery_resume_stage`)

- **Surface:** Sticky pin=`sound_design_plan` after SDP sealed; remutate→transitions while G1 open.
- **Why:** Sticky held sealed SDP; remutate honor yanked to transitions while G1 still open.
- **Test:** `tests/test_i4_sticky_sealed_vo_walk.py`.

#### i5 — Sealed VO expensive lease (origin: `expensive_stage_lease_active`)

- **Surface:** `premature_complete:phase_a_edl` ×3 pinned `vo_synthesize` while G1 clear.
- **Why:** Sealed synthesize still held expensive lease via stale job/mtime.
- **Test:** `tests/test_i5_sealed_vo_lease.py`.

#### i6 — premature_cap hard-fail idle spin (origin: `web/runner.py`)

- **Surface:** `from_stage=edl` returned `ok:False` / `pinned_to` without worker → idle spin.
- **Why:** Automation received HTTP 200 + ok:False; driver treated as success and spun.
- **Fix:** Rewrite premature_cap pin + recompute stage_ids; driver follows `pinned_to`.
- **Test:** `tests/test_i6_premature_cap_auto_rewrite.py`.

#### i7–i7j — HAU speech-first music chain (origin: HAU admit + walk + ESR + MUST_PRECEDE)

- **Surface:** Hollow Finished `music_palette`; premature_complete:music_epoch; MusicGen refused `assembly_preview_only` then walk continued; MUST_PRECEDE→mmaudio; theme/SFX hard-blocks.
- **Why:** With only `assembly_preview`, music was correctly refused, but walk/ESR/MUST_PRECEDE/seed-front/theme/SFX gates kept yanking away from speech-first mix or returning hollow Finished.
- **Fix:** Redirect preview_only→mix-only; skip MUSIC inside speech-first walk; ESR prefers mix; raise if ESR didn’t land; soft theme/SFX under speech-first.
- **Test:** `tests/test_i7_hau_speech_first_music.py`.

#### i8 — SDP duration repair under hard VO freeze (origin: `_repair_sdp_asset_durations`)

- **Surface:** Emphasis 2.2s vs 5–12 band; repair “changed” but file stuck.
- **Why:** Hard VO freeze silently no-op’d SDP writes without owned End-A reason / bare `stage_key`.
- **Fix:** End-A `sdp_duration_band_repair` + `commit_sound_design_plan_doc`.
- **Tests:** `test_sdp_duration_repair_writes_with_stage_key`, `test_sdp_duration_repair_persists_under_hard_seat_freeze`.

### 13170 bottom line

Roots were **VO walk / omit honesty**, **driver premature_cap + sticky/lease**, **speech-first music admit**, and **End-A SDP duration**. Music hollow Finished was mostly an echo of speech-first admit + walk continue.

---

# 4. exec_13177 — four true roots (layup, air_script, VO synth, SDP)

**run_id:** `exec_13177_d19c15b58ab4_20260923T001031Z`  
**Outcome:** Local ship. Delight **0.9725**. Master ~41.1 min / 226 MiB.  
**Ledger:** 476 entries, 97 unique predicates.  
**Deep analysis:** `full_auto_forensics_error_analysis_exec_13177.md`  
**Post-ship residuals 1–6:** closed (CTA↔floor, hard-freeze unsatisfiable, omit WAV protect, FMR cover, spoken_copy soften, stale soft-freeze test).

### Exact root-cause stage count (late campaign)

| Kind | Count |
|------|------:|
| Distinct **root-cause stages** | **4** |
| High-noise **symptom stages** | **5** |
| Late product patches (i9–i15) | **7** major (+ i12b reload) |

### The four origin stages

```text
#45 nugget_layup_compose  ──CTA omit + hosted floor shortfall──► sanitize / transitions / G1 / early edl
#42 air_script_compose    ──stale required-orientation waive───► edl opening_orientation_inaudible
#55 vo_synthesize         ──WAV exists but omit/bind/StageInfo──► edl / assembly_preview thrash
#53 sound_design_plan     ──off-selection beds + mix_seated invent──► music_palette / narrative audit logs
```

### Early interventions (i1–i8) — producers before the late VO/SDP storm

| iN | Surface | Origin | Why |
|----|---------|--------|-----|
| i1 | `authority_denied:mark_done:pending_writes` | early flush/mark_done | Pending writes not flushed before seal |
| i2 | gap_report `pending_only` | `gap_framing_compose` | Missing rationale masked as pending |
| i3 | selection_commit_refused owner=junction | `nugget_layup_compose` selection | Layup needed selection ALLOW / HR-2 |
| i4 | `selection_cta_omit` budget_exhausted | layup / `llm_simple` CTA | CTA omit raised into budget exhaust; later one in-invoke retry |
| i5 | bridge_completeness ×3 | bridge mint under End-A | Missing End-A mint path |
| i6 | `layup_compose_shards_pending` under hard freeze | layup / stage_completion | Final shard treated as blocking |
| i7 | vo_g1 missing lines | G1 check vs omit ledger | G1 ignored omit ledger |
| i8 | edl_narrative_qc order≠selection | `nle_state.apply_nle_to_selection` | Full-spine `sequence_order` dump polluted QC |

These mattered, but the **campaign-defining thrash** was i9–i15.

### Late root causes (detailed)

#### Root A — Stage **#45 `nugget_layup_compose`** (largest cascade)

- **Ledger hits at stage:** 97 (highest in run).
- **What started here**
  1. CTA omit (`selection_cta_omit`) dropped natives the rest of the pipeline still needed for opening / host obligations.
  2. Hosted VO floor unmet (`hosted_vo_floor_unmet`) under G-Framing Yes (need ≥3). Hard freeze then blocked invent-style reseat.
- **Why it is a root:** Later stages did not invent the shortage; they only noticed missing hosted lines / waived CTA material / incomplete seed.
- **Echo stages:** `#47 refinement_agenda` (84 — almost pure wait), `#51/#52` sanitize→transitions identical storm, early `#55` / `#58` G1 open.
- **Patch:** **i10** — End-A `reseated_active_hosted_vo_for_wav` when active≥need but WAV short; pin `hosted_vo_wav_coverage` → `vo_synthesize`. (Shortage itself still originated at #45.)
- **Post-ship residual:** CTA↔floor coupling (**i16** / `test_i16_cta_floor_anchor_keep`) — CTA prune must keep natives that still anchor floor-counting host lines.
- **Hard-freeze true shortage:** `active < need` now escalates `hosted_vo_floor_unsatisfiable` (empty heal pin) instead of layup thrash — by-design, not invent.

#### Root B — Stage **#42 `air_script_compose`** (failed loudly at `#58 edl`)

- **Surface:** `opening_orientation_inaudible` (expected 1, heard 0) ×4 ERROR at **edl**.
- **Origin:** Air-script / omit / waive handling of a **required** CTA-orientation scrap.
- **Why:** Stale `tier_d_logged_waive` / `execution_contract_waive` treated as durable waive while `meta.required`; seats kept line in `omitted_line_ids`; heal playbook skipped revive unless resume=`edl`; soft-freeze omit persist no-op left seats stale after gap revive.
- **Why not #58:** EDL correctly detected inaudible orientation; the line was already removed from the audible plan upstream.
- **Patch:** **i9** — required+not-omitted → not waived; revive clears stamps + reseats; playbook always revives.
- **Test:** `tests/test_i9_required_orientation_stale_waive.py`.

#### Root C — Stage **#55 `vo_synthesize`** (independent after WAVs existed)

- **Ledger hits:** 69.
- **Distinction:** #45 = “never got enough / right hosted lines.” #55 = “got lines and WAVs, then threw them away or refused to count them.”
- **i11 — Omit+WAV flag drift:** Clamp expanded omitted without syncing gap; repair `write_json` stripped omit flags; WAV-backed lines stayed omitted.
- **i12 / i12b — Seated omit purge + StageInfo:** Stale `layup_skip` omit purged seated clips/WAVs; StageInfo only declared `vo_pickup/synthesized/` so top-level `vo_pickup/*.wav` dropped on flush; **serve reload required** (stale server re-applied old purge).
- **i13 — Bind heal omit-wins:** Chatterbox wrote WAV then `invalid_json_stdout` (pkg_resources warning); bind heal omit-wins `seated_bind_synth_failed` despite on-disk audio.
- **Echo:** `#57 edl_narrative_audit`, `#58 edl`, `#59 assembly_preview` (“VO coverage not rendered: 003c”), console `flush_refuse:vo_fail_open_not_success` ×3.
- **Tests:** `test_i11_omitted_wav_reseat`, `test_i12_seated_omit_purge_protect`, `test_i13_bind_heal_wav_accept`.
- **Post-ship residual:** omit protect also unions WAV stems on disk + fail-closed on protect load failure.

#### Root D — Stage **#53 `sound_design_plan`** (late, independent of VO floor)

- **i14 / i14b — Off-selection bed seeds:** Selection shrunk; stale bed_coverage seed still pointed at `seg_028`; drop_outside_selection ran too late (after coverage seed/validate); palette `segment_ids` needed prune; one validated write reverted.
  - **Surfaced at:** `#61 music_palette_compose` (only 2 ledger hits, each a hard stop).
- **i15 — Mix-seated invent refuse:** Mix already seated assembly; `order_reconcile` denied narrative_plan persist under `mix_seated`; invent fail-closed even with `assembly.wav` + SDP present; missing `_meta.producer_stage` made “SDP present” checks fail.
  - **Often logged under:** `#57 edl_narrative_audit` (echo attribution).
- **Tests:** `test_i14_sdp_bed_off_selection`, `test_i14b_sdp_compose_write`, `test_i15_mix_seat_sdp_reconcile`.

### High-noise symptom stages (13177 — not roots)

| Stage | Hits / role | Actually caused by |
|-------|-------------|-------------------|
| `#47 refinement_agenda` | 84 | Waiting on incomplete #45 |
| `#58 edl` | 48 | Detector for #42 / #45 / #55 |
| `#52 transitions` | 18 | Floor unmet leak + recovered `spoken_copy_guard` (Performance) |
| `#59 assembly_preview` | 4 | Echo of #55 omit/bind |
| `#40 full_master_ranking` | 19 | Recovered hard-freeze / ordered∪excluded barrier (post-ship cover fix) |

### Interventions → origin map (13177)

| Intervene | Origin stage | One-sentence fix |
|-----------|--------------|------------------|
| i9 | #42 air_script (surfaced #58) | Required orientation not durably waived; revive+reseat |
| i10 | #45 condition → #55 sanitize | Reseat active hosted VO for WAV under hard freeze |
| i11–i13 | #55 | Contract/omit/StageInfo/bind honor on-disk WAV |
| i14–i15 | #53 (surfaced #61 / audit logs) | Drop off-selection beds early; skip invent-fail when assembly+SDP exist |

### 13177 bottom line

If you only remember four numbers from this run: **#45, #55, #42, #53**. Everything else was follow-on thrash, seed-order waiting, or recovered noise. Residuals 1–6 after ship closed the remaining CTA↔floor / hard-freeze unsatisfiable / omit WAV / FMR cover / spoken_copy / stale-test gaps.

---

# 5. Archive — exec_11871 (ownership + junction↔mix era)

**run_id:** `exec_11871_d19c15b58ab4_20260916T002245Z`  
**Interventions:** i1–i54. Homunculus 0.1.0.  
**Dominant volume:** `junction_snip_qa` ⇄ `mix` deadlock (thousands of `incomplete_cut*` lines) + fail-closed ownership (`authority_denied` storm — new vs prior campaign).

### Origin bands (from archived end report)

| Band | Meaning | Example origins |
|------|---------|-----------------|
| **OWN** | Write authority / catalog | G0 flush/signoff, volley pack, vernacular/connector_fuse manifest, ranking bridges, layup/gap ownership, hard_freeze denials from wrong writers, SDP cue writers, sfx manifest, StageInfo publish files |
| **SEAT** | Seat order & gate deadlock | `junction_recut_before_first_mix`, missing assembly preflight, conductor seed-front, freeze-exempt omit, inner remaster markers, stale assembly stranding recut |
| **CONTENT** | Audible product defect | Hosted VO floor under G-Framing, missing VO pickup WAV, overlap after bind, hard-keep fuse refuse, chapter bleed skip |
| **SHIP** | Ship-gate honesty | Loudnorm vs verify path, delight/seam_autopsy ownership, JPEG as JSON, undeclared publish outputs, true-peak after loudnorm, delight audit flush drop |
| **OPS** | Operator/driver scaffold | Deferred pairs sync lock jam, version-mismatch operator scaffold |

This campaign established the fail-closed ownership constitution that later campaigns still fight (and extend) under hard freeze / End-A.

Full i1–i54 table: `.cursor/plans/full_auto_forensics_end_report.md` (Prior campaign archive).

---

# 6. Sibling HINT / partial executions (not full intervene logs)

These share the mohan tape and appear under `ASSETS/executions/` but lack a full forensics intervene SSOT. Use them as **cousin signals**, not as primary root attribution.

| Exec | Dominant signal | Relation to shipped campaigns |
|------|-----------------|-------------------------------|
| **13161** | FREEZE + UNCLASS; narrative_plan hard_freeze | Cousin of 13167 i9 |
| **13163** | VO_LADDER_PARTIAL (seed_order adjudicate→synth storm) | Cousin of 13167 i4–i7 |
| **13165** | premature vo_g1; narrative hard_freeze; wrong pin | Cousin of 13170 pin/lease + 13167 freeze |
| **13168** | Partial soak (gap_framing ownership, budget thrash) | Historical soak notes — not full-auto forensics |
| **13160/62/64/66/69/71–76** | Fresh twins / aborted / driver restarts | Usually pair with the odd “campaign” exec above |

---

## Master index: origin stage → campaigns that hit it

| Origin stage / module | 11871 | 13159 | 13167 | 13170 | 13177 |
|-----------------------|:-----:|:-----:|:-----:|:-----:|:-----:|
| `artifact_ownership` / StageInfo | ●●● | ● | ● | | ● (vo_pickup) |
| `nugget_layup_compose` / CTA / floor | ● | ● | ● | | ●●● |
| `air_script` / omit waive / orientation | ● | | | ● (omit-wins) | ●● |
| `vo_synthesize` / contract / bind / omit_ledger | ● | | ● | ● | ●●● |
| `sound_design_plan` / SDP repair / dens / invent | ● | | ●●● | ● | ●● |
| `junction_snip_qa` / precedes_mix / remaster | ●●● | ●●● | ●● | | |
| `mix` hollow mark_done / resume | ● | ● | ●●● | ● (speech-first) | |
| Driver premature_cap / sticky / lease / ESR | ● | ● | ● | ●●● | |
| `spoken_copy_guard` / transitions | | | ● | | ● (residual) |
| `full_master_ranking` membership | ● | | ● | | ● (residual) |
| Ship / PMQ / delight flush | ●● | ● | ● | | |

● = hit · ●● = significant · ●●● = campaign-defining

---

## Operator cheat-sheet: never patch the echo first

| If you see… | Do **not** start at… | Start at (origin)… |
|-------------|----------------------|--------------------|
| `hosted_vo_floor_unmet` on transitions/sanitize | `transitions` | `nugget_layup_compose` + sanitize reseat path |
| `opening_orientation_inaudible` on edl | `edl` alone | air-script waive / omit / revive |
| `VO coverage not rendered` on assembly_preview | `assembly_preview` | `vo_synthesize` omit/bind/StageInfo |
| music_palette density / off-selection bed | only palette | `repair_sound_design_plan` / SDP seeds |
| mix ↔ junction ping-pong | random remaster | `precedes_mix` + assembly freshness + resume |
| hollow Finished music under speech-first | MusicGen stub | HAU admit + walk MUST_PRECEDE / ESR |
| `authority_denied` storm | consumer stage | ownership ALLOW / End-A reason / freeze epoch |
| budget_exhausted / identical×3 | budget alone | usually the producer already listed above |

---

## Related documents

| Doc | Role |
|-----|------|
| [full_auto_forensics_run.plan.md](full_auto_forensics_run.plan.md) | Campaign protocol (fresh once, continue on bug) |
| [full_auto_forensics_state.md](full_auto_forensics_state.md) | Live intervene log (currently 13177) |
| [full_auto_forensics_error_analysis_exec_13177.md](full_auto_forensics_error_analysis_exec_13177.md) | Deep 13177 roots + residuals closed |
| [full_auto_forensics_end_report_exec_13177.md](full_auto_forensics_end_report_exec_13177.md) | 13177 ship summary |
| [full_auto_forensics_end_report_exec_13170.md](full_auto_forensics_end_report_exec_13170.md) | 13170 ship summary |
| [full_auto_forensics_end_report_exec_13167.md](full_auto_forensics_end_report_exec_13167.md) | 13167 ship summary |
| [full_auto_forensics_end_report.md](full_auto_forensics_end_report.md) | 13159 + 11871 archive |

---

*Generated from campaign end reports, state intervenes, exec_13177 error analysis, per-run `forensics_errors.md` ledgers, and cascade test attributions. Intervene numbers are campaign-local.*

---

# Codebase coverage audit (2026-09-23)

**Question answered:** Against **current HEAD**, which roots in this report are actually patched, which are only partly closed, and what remains open?

**Method:** Map each report root → product symbols + cascade tests → run a representative suite under `MUX_FORENSICS=0`. Status legend:

| Status | Meaning |
|--------|---------|
| **FIXED** | Product code + cascade test both present; representative suite green |
| **SUPERSEDED** | Original 13159-era expectation replaced by a newer constitution (not a live product hole) |
| **PARTIAL** | Fix landed but test drift, thin coverage, or ops footgun remains |
| **OPEN** | Report root still vulnerable / not found in code |
| **NEW RISK** | Not in original report roots; present on HEAD after later work |

**Cascade spot-check (this audit):** Core i9–i16 / End-A / FMR / spoken_copy / mix-seat / premature_cap / sticky / lease suites green. Test debt from Always-HAU constitution drift was rewritten (2026-09-23): `test_junction_does_not_precede_when_assembly_missing` + stale-assembly companion; `test_filter_phase_a_before_speech_first_mix_when_unsealed` (Phase-A before speech-first). Both files pass under `MUX_FORENSICS=0` (17 tests).

---

## 1. What was covered and patched (FIXED)

### A. Layup / hosted VO floor

| Report root | HEAD evidence | Cascade |
|-------------|---------------|---------|
| CTA omit orphans floor targets (#45 / residual) | `media_ip_cta.floor_anchor_keep_ids`, `restore_floor_anchor_natives`; wired into CTA prune / heal / `commit_layup_cta_selection` | `tests/test_i16_cta_floor_anchor_keep.py` |
| Hollow scrub dropping floor lines (13167 i1) | `nugget_layup._scrub_foreign_before_vo_for_hollow_preserve` re-admits to hold `min_active` | `tests/test_nugget_layup.py` (hollow_preserve_floor_retained_foreign) |
| Hard-freeze true shortage thrash (active &lt; need) | `vo_contract._record_hosted_floor_unmet` → `stamp_hosted_vo_floor_unsatisfiable` / empty heal pin | `tests/test_layup_compose_hardening.py::test_hosted_vo_floor_unsatisfiable_heal_pin_empty`; End-A refuse-notes |
| WAV short while active ≥ need (13177 i10) | End-A `reseated_active_hosted_vo_for_wav`; pin `hosted_vo_wav_coverage` → `vo_synthesize` | `tests/test_i10_hosted_vo_wav_coverage.py` |
| Framing floor need / topup | `gap_fill_eligibility.min_synthetic_vo_lines`; `nugget_layup._framing_floor_topup` | `test_f3_layup_vo_contract`, gap framing / layup suites |

### B. Air-script / required orientation (13177 i9)

| Report root | HEAD evidence | Cascade |
|-------------|---------------|---------|
| Stale tier-D / execution_contract waive on required line | `air_script._orientation_line_waived` refuses waive when required; `opening_orientation.clear_stale_orientation_waive_stamps` | `tests/test_i9_required_orientation_stale_waive.py`, `tests/test_orientation_waive_constitution.py` |
| Heal playbook skips revive | Playbook always revives on `opening_orientation_inaudible` | `test_playbook_orientation_inaudible_always_revives` |

### C. VO authority after WAV exists (13177 i11–i13 + omit residual)

| Report root | HEAD evidence | Cascade |
|-------------|---------------|---------|
| Omitted+WAV flag drift | `vo_contract.repair_vo_contract_drift` reseat; clamp stamps gap omit; persist_frozen | `tests/test_i11_omitted_wav_reseat.py` |
| Seated omit purge + seat-lag WAV | `omit_ledger`: protect seated ∪ `_wav_backed_vo_line_ids`; fail-closed skip purge on load fail | `tests/test_i12_seated_omit_purge_protect.py` |
| Undeclared `vo_pickup/*.wav` flush drop | `web/stages.py` `vo_synthesize` StageInfo includes `vo_pickup/` | Covered with i12 |
| Bind heal omit-wins after false synth fail | `vo_bind_authority` accepts stem WAV; never omit when WAV present; force-clear `seated_bind_synth_failed` | `tests/test_i13_bind_heal_wav_accept.py` |

### D. SDP honesty (13167 dens, 13170 duration, 13177 i14–i15)

| Report root | HEAD evidence | Cascade |
|-------------|---------------|---------|
| Dens wipe of planned beds (13167 i3) | `soundscape_policy._merge_planned_bed_slots` | `test_score_cue_slots_preserves_planned_sdp_beds_beyond_dens_cap` |
| Off-selection bed seeds (13177 i14/i14b) | Pre-seed drop in `artifact_repairs`; palette prune / direct-write | `test_i14_sdp_bed_off_selection`, `test_i14b_sdp_compose_write` |
| Mix-seated invent refuse (13177 i15) | Skip invent-fail when `assembly.wav` + SDP present; stamp `_meta.producer_stage` | `tests/test_i15_mix_seat_sdp_reconcile.py` |
| SDP duration silent no-op under hard VO freeze (13170 i8) | End-A `sdp_duration_band_repair` + `commit_sound_design_plan_doc` | `test_sdp_duration_repair_*` in `test_i7_hau_speech_first_music.py` |

### E. Junction / mix seat (13159 + 13167 i11 chain)

| Report root | HEAD evidence | Cascade |
|-------------|---------------|---------|
| Hollow mark_done:mix (mtime) | `air_order.ensure_assembly_mtime_seats_edl` before mark_done | `tests/test_i11_mix_mark_done_seats_mtime.py` |
| assembly_stale pin→junction | `resolve_assembly_stale_resume` → `mix` | same file |
| path_to_master prefers junction when stale | pins mix when assembly_stale | same file |
| Ledger sha ≠ final | `write_render_ledger` fingerprints `final_path` | same file |
| Remaster under junction pending | nested `run_nested_staged_stage("mix")` | same file |
| Remaster-only ≠ incomplete_cut | publishability / heal_routing remap | `test_i11_premix_commitment_diverge_not_incomplete_cut` |
| premature_complete:mix_seat after seated | advance past seated mix | `test_i11_advance_past_seated_mix` |
| Hollow finalize / PMQ missing | PMQ persists when delight loud-fails | `test_i11_pmq_persists_when_delight_fails` |
| Junction remaster drops mix QC (13159 i9) | promote mix QC side-effects / reconcile ship-bar | `test_i9_junction_remaster_promotes_mix_qc` |
| Stale assembly must precede (part of 13159 i8) | `junction_precedes_mix` True when assembly **exists and stale** | `tests/test_mix_junction_seat.py`, `test_hau_footgun_harden.py` |

### F. Driver / premature / sticky / lease / adopt (13159 i6*, 13170 i4–i6)

| Report root | HEAD evidence | Cascade |
|-------------|---------------|---------|
| Adopt layup with DENY `stage_key=edl` | `adopt_layup_plan_to_selection` default `stage="nugget_layup_compose"` | `test_edl_adopt_must_use_layup_owner_not_edl_stage_key` |
| Freeze-sticky re-invoke layup/SDP | `FREEZE_STICKY_SEED_STAGES_CORE` includes layup + SDP | `test_seed_policy_hard_freeze_sticky_all_core_stages` |
| Sticky sealed pin / remutate vs G1 | sticky clear when seed-complete; remutate skip when G1 open | `test_i4_sticky_sealed_vo_walk`, category_b conductor sticky test |
| Sealed VO expensive lease | sealed synthesize not leased | `test_i5_sealed_vo_lease` |
| premature_cap idle spin | automation rewrites pin + follows `pinned_to` | `test_i6_premature_cap_auto_rewrite` |
| High-gap omit demote (13170 i3) | demote uncovered high gaps; synth stability pin | `test_i3_omit_demote_high_gap` |
| Omit-wins execution_contract_waive (13170 i2) | durable omit-wins markers | `test_execution_contract_waive_survives_hosted_floor` |
| HC-3 pending invent twin (13170 i1) | write_mirrored no invent | `test_hc3_pending_overlay` |
| ESR sound_design vo_wavs leapfrog (13167 i8) | pin matcher ignores vo_wav freshness for sound_design* | `test_sound_design_vo_finalize_pin_ignores_vo_wav_freshness` |
| Budget epoch after product patch (13167 i7) | `stamp_budget_epoch` / identical reclaim | `test_budget_epoch_resets_count_attempts_after_product_patch`, BUD-1 suites |
| HAU speech-first music refuse + walk continue (core of 13170 i7) | `allow_speech_first_mix` / hold speech-first; ESR hollow→mix; soft theme/SFX | Most of `test_i7_hau_speech_first_music.py` **green** (one stale filter case — see PARTIAL) |

### G. Ownership / FMR / spoken copy / early 13177 i1–i8

| Report root | HEAD evidence | Cascade |
|-------------|---------------|---------|
| Narrative plan align under hard_freeze (13167 i9) | ALLOW `edl_narrative_audit` → narrative_plan + `narrative_metadata_align` | End-A / narrative hard-freeze suites |
| FMR ordered∪excluded orphans (#40 residual) | `open_shape_repair.cover_ranking_manifest_membership` on FMR persist | `test_cover_ranking_manifest_membership_excludes_orphans` |
| Hard-freeze CTA child invent | `_persist_recut_children` / `materialize_split_children_into_manifest` skip invent | `test_hard_freeze_skips_cta_child_invent` |
| `spoken_copy_guard` Performance + mid-sentence (#52 residual + 13167 i10) | `_ENTITY_IGNORE` includes Performance; `_soften_mid_sentence_fallback`; remutate opener repair | `test_performance_*`, `test_mid_sentence_fallback_*`, `test_i10_mid_sentence_transition_repair` |
| Stale soft-freeze CTA skip test (#6 residual) | Deleted `test_cta_commit_skipped_under_soft_freeze`; soft freeze commits | `test_soft_freeze_still_commits_cta`, `test_hard_freeze_skips_cta_commit` |
| pending_writes before mark_done (i1) | `mark_done` auto-flush pending | `test_i1_g0_flush_before_gate`, stage_completion heal |
| Layup selection ALLOW / HR-2 (i3) | ownership catalog + heal_routing | `test_layup_selection_commit_ownership` |
| Layup shard pending (i6) | final-shard non-blocking | `test_i6_layup_shard_pending` |
| G1 honor omit ledger (i7) | G1 consults omit ledger | `test_i7_g1_omit_ledger_freeze` |
| NLE full-spine sequence_order dump (i8) | ignore full-cover dumps | `test_apply_nle_ignores_full_spine_sequence_order_dump` |
| Bridge completeness End-A mint (i5) | `bridge_completeness_mint` allowlisted | End-A / f4 bridge glue |
| Mid adjudicate hollow mark_done (13167 i4) | `auto_complete=False` per batch | `test_run_adjudicate_batches_does_not_mark_done_mid_batch` |
| Intro unwrap / gendered pronoun (13167 i5–i6) | unwrap envelope; scrub pronouns | dedicated intro/spoken scrub tests |
| Critical remaster mislabeled budget (13159 i7) | incomplete_clause retry path | `test_jsq_critical_remaster_path` (other cases; see SUPERSEDED for assembly-missing) |

### H. Ownership-era archive (11871) — treated as landed constitution

The i1–i54 OWN/SEAT/CONTENT/SHIP table in the archived end report is the fail-closed ownership era. Current tree still carries those ALLOW rows, freeze epochs, junction omit seats, ship StageInfo declarations, etc. They are not re-audited line-by-line here; treat as **FIXED baseline** that later campaigns extend (End-A, HAU, heal clinic).

### I. Heal Clinic (post-report, but closes cousin thrash classes)

Not listed as forensics campaign roots, but HEAD now implements five heal SSOTs that address thrash shapes those campaigns often *echoed*:

| Pattern | Module | Status |
|---------|--------|--------|
| wrong_pin | `heal_pin_authority.resolve_heal_from_stage` | implemented |
| leapfrog_resume | Admit Constitution | implemented |
| hollow_pass | `done_authority.try_mark_done` | implemented |
| heal_validate_stage_fail | `heal_success.finalize_heal_success` | implemented |
| post_heal_budget_thrash | `heal_post_accounting.finalize_post_heal_accounting` | implemented |

Source: `.cursor/heal-clinic/heal_readiness.md` (Wave 3 complete). Residuals there are allowlist/exception drift and P6 (walk `max_invokes` not epoch’d on recover) — see OPEN below.

---

## 2. SUPERSEDED (not open product bugs — update tests)

| Report claim | What HEAD does now | Evidence |
|--------------|--------------------|----------|
| **13159 i8:** missing `assembly.wav` alone ⇒ `junction_recut_precedes_mix` True | **Missing assembly alone does not precede** — mix mints the first seat. Junction precedes only for live incomplete cuts, remaster-in-flight (non–music_epoch), or **existing stale** assembly. | `mix_junction_seat.junction_precedes_mix`; cascade: `test_junction_does_not_precede_when_assembly_missing` + `test_junction_precedes_when_existing_assembly_is_stale` (**rewritten 2026-09-23**) |

---

## 3. PARTIAL (patched, but gaps remain)

| Item | Why PARTIAL | What to do |
|------|-------------|------------|
| **Serve / StageInfo reload (13177 i12b)** | Product declares `vo_pickup/`; live forensics still needs **process reload** after StageInfo patches or old purge/drop recurs | Ops checklist; not fixable by code alone |
| **CTA omit LLM retry (13177 i4)** | Product path exists (one in-invoke retry / demote); thin dedicated cascade naming | Optional named regression if CTA budget thrash returns |
| **Gap `pending_only` rationale (13177 i2)** | Heal surfaces `flush_error` over pending_only mask; dedicated “missing rationale” unit not found | Acceptable if flush thrash stays quiet |
| **Hard-freeze floor unsatisfiable** | Correctly FIXED as escalate-empty-pin — but a **true** shortage still blocks ship by design if layup/CTA leave active &lt; need before freeze | Ensure floor anchors (i16) + topup fire earlier; treat unsatisfiable as honest stop, not thrash |

HAU speech-first filter test debt (**closed**): `test_filter_phase_a_before_speech_first_mix_when_unsealed` — unsealed prefers Phase-A hole (never music beds); sealed + VO-ready keeps `mix`.

---

## 4. Still open / remaining

### A. From this report’s original roots

| Item | Status | Notes |
|------|--------|-------|
| Product roots in §§1–4 of this document (layup floor, orientation waive, VO after WAV, SDP dens/beds/invent, mix seat chain, premature/sticky/lease, FMR cover, spoken_copy Performance) | **CLOSED on HEAD** | See FIXED tables |
| Stale cascade expectations (assembly-missing precede; speech-first filter vs Phase A) | **CLOSED (tests rewritten)** | See §2 SUPERSEDED + HAU filter note in §3 |
| Live serve reload after StageInfo / ownership patches | **OPEN (ops)** | Recurs if forgotten mid-campaign |

### B. New / adjacent risks not closed by forensics campaign patches

| Risk | Why it matters | Where tracked |
|------|----------------|---------------|
| **Heal Clinic residual P6** | Walk `max_invokes` not reset on recover; sticky still sealed/token-only; empty `POST_HEAL_EPOCH_ALLOW` by design — misuse reopens budget thrash | `.cursor/heal-clinic/heal_readiness.md` |
| **Pin / playbook allowlist drift** | New navigators that bypass `resolve_heal_from_stage` or widen `RECOVER_PLAYBOOK_ALLOW` reintroduce wrong_pin / false recovered | Heal Clinic readiness residuals |
| **XC-HOLLOW-01 and failure_catalog OPEN_RISK crosscuts** | Many analysis stages still lack incompleteness/heal coverage; G1 fail-open; music-epoch / delight-authoritative / heal-navigate-pins still flagged OPEN_RISK in catalog | `.cursor/plans/failure_catalog/crosscuts.md` |
| **`gap_vo_rebudget.py`** | Post-ranking VO density re-budget — new coupling to floor/topup honesty; not in original forensics root index | `src/interview_mux/gap_vo_rebudget.py` |
| **Listen-delight / live soak** | Explicitly outside Heal Clinic claim; tape quality and first-try finish not guaranteed | heal_readiness operator verdict |
| **Sibling HINT cousins (13161/63/65)** | Not intervene-logged; VO ladder / freeze / wrong-pin cousins may still appear on Partial/HINT | named exec HINT only |
| **Fresh exec after HEAD** | No post-residual full-auto forensics ship on this tape since residuals 1–6 closed | Recommend next `MUX_FRESH=1` campaign to validate quiet #45/#55/#53 |

### C. Intentionally not “open bugs”

- **G-Publish S3 consent** — operator gate; local ship OK when PMQ `publish_allowed=True`.
- **True hosted floor shortage under hard freeze** — escalates `hosted_vo_floor_unsatisfiable` (empty heal pin). That is the constitution, not a missing patch.
- **Incomplete-after-conductor handoffs** — walk bookkeeping, not product defects.

---

## 5. Scorecard (report roots vs HEAD)

| Campaign | Defining roots | HEAD status |
|----------|----------------|-------------|
| **11871** | Ownership + junction↔mix deadlock era | FIXED baseline (constitution) |
| **13159** | Layup adopt/sticky, precedes_mix, remaster QC | FIXED; missing-assembly precede **SUPERSEDED** |
| **13167** | SDP dens, hollow mark_done, mix seat chain, mid-sentence, narrative hard_freeze | FIXED |
| **13170** | VO omit/high-gap, sticky/lease, premature_cap, HAU speech-first, SDP duration | FIXED core; **1 PARTIAL** speech-first filter test drift |
| **13177** | #45 floor/CTA, #42 orientation, #55 VO false-fail, #53 SDP beds/invent + residuals 1–6 | FIXED |

| Bucket | Count (approx) |
|--------|----------------|
| Report product roots **FIXED** | ~48 checklist items |
| **SUPERSEDED** | 1 (missing-assembly precede) |
| **PARTIAL** | ~3 (serve reload ops, thin CTA-retry naming, by-design unsatisfiable) |
| Report product roots still **OPEN** | **0** |
| **NEW RISK / catalog OPEN_RISK** | Heal Clinic residuals + failure_catalog crosscuts + no post-residual fresh ship |

---

## 6. Recommended next actions (priority)

1. **Fresh forensics soak:** one `MUX_FRESH=1` full-auto on the mohan tape with residuals 1–6 + Heal Clinic on HEAD — prove quiet #45/#55/#53 without serve-reload footguns.
2. **Do not reopen** hard-freeze invent for true floor shortage; keep unsatisfiable escalate.
3. **Track catalog OPEN_RISK** (XC-HOLLOW-01, G1 fail-open, music-epoch, delight-authoritative) separately from forensics campaign roots — they are broader than the exec_131xx intervene set.
4. **Guard Heal Clinic allowlists** when adding navigators or recover playbooks.

~~Done: rewrite Always-HAU stale cascades (`test_junction_*`, `test_filter_phase_a_before_speech_first_mix_when_unsealed`) — 17/17 green under `MUX_FORENSICS=0`.~~

---

*Audit date: 2026-09-23. Based on HEAD product symbols, cascade collection under `MUX_FORENSICS=0`, Heal Clinic readiness, and failure_catalog crosscuts. Does not claim a new fresh ship has re-proven the tape end-to-end after residuals closed.*
