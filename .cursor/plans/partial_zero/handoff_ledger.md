# Handoff ledger — Partial Zero

**SSOT:** `src/interview_mux/v2/phases.py`, `src/interview_mux/delivery_guardrails.py` (`MUST_PRECEDE`, `producer_ready` / `seed_stage_complete`)  
**Ready meaning (code):** `producer_ready` ≡ `seed_stage_complete` ≡ `is_done` ∧ `stage_outputs_present` ∧ no `stage_artifact_incompleteness` — **no** `artifact_exists` escape.  
**brain / mode:** 0.2.0 · partially_accelerated  
**status:** bootstrap seed — Critical Five deep analysis still pending

---

## Phase boundaries (`phases.py`)

Journey cuts are artifact seams. Each phase owns a contiguous seed-order slice (or a gate / NLE shell).

| # | producer phase | consumer phase | boundary artifact / gate | ready meaning | freeze / ownership notes | cousin risk | linked junction |
|--:|----------------|----------------|--------------------------|---------------|--------------------------|-------------|-----------------|
| P1 | `start` | `prepare` | interview audio selected; optional preclean offer | UI selection only | no stage_done | — | — |
| P2 | `prepare` | `fix_transcript` | `transcript/review_queue.json` (+ probe) | prepare stages seed-complete | G0 human; do not rewind after close | hollow_done on review_build | — |
| P3 | `fix_transcript` | `understand-a` | G0 closed | operator gate cleared | timeline lock after G0 | premature G0 skip | — |
| P4 | `understand-a` | `understand-b` | `segments/manifest.json` (+ boundaries) | segment_classification seed-complete | classified tape protected | hollow classification | — |
| P5 | `understand-b` | `understand-c` | refined segments + posture | connector_fuse_pass seed-complete | shared `content_brief` ownership | reanchor thrash | — |
| P6 | `understand-c` | `fill_gaps` | Shape / mastering plan | `mastering_plan_synthesize` seed-complete | plan confirm still in fill_gaps | Shape hollow → premature pin | — |
| P7 | `fill_gaps` | `plan_rank` | G1 (`g1_vo_pickup`) + gap artifacts | G1 cleared / skip; gap chain seed-complete | optional phase; VO path SSOT | **vo-ladder-partial** | J-vo-ladder-partial |
| P8 | `plan_rank` | `edit` | air/transitions sealed | `transitions` seed-complete | NLE optional shell | seat freeze during edit | J-freeze-constitution |
| P9 | `edit` | `sound` | (pass-through if NLE skipped) | same as plan_rank exit | GUI Take best / Skip | optimizer promote skip freeze | J-freeze-constitution |
| P10 | `sound` | `build` | SDP + adjudication | `vo_line_adjudicate` seed-complete | SDP cue_slots vs dens cap | **sdp-cue-slots** | J-sdp-cue-slots |
| P11 | `build` | `ship` | EDL + assembly + junction | `edl` seed-complete; mix/junction seating rules | mix optional under recut-precede | **mix-junction-precede**, assembly freshness, hollow junction | J-mix-junction-precede · J-assembly-freshness · J-hollow-done |
| P12 | `ship` | (done / G-Publish) | `master/master.wav` + PMQ | `committed_master_wav` + publish envelope | G-Publish human; ship wait split | **post-master-wait** · five-meanings-of-done | J-post-master-wait |

**Critical Five** (deep-analysis priority): `fill_gaps` · `plan_rank` · `sound` · `build` · `ship`.

---

## Critical Five — internals (stage slices + key artifacts)

### `fill_gaps` (optional + G1)

| Stage | Primary artifacts (PROTECTED / ownership) |
|-------|-------------------------------------------|
| `missing_framing` | framing posture / missing set |
| `mastering_plan_confirm` | confirmed mastering plan |
| `gap_framing_compose` | gap framing lines |
| `delivery_brief_build` | `understanding/delivery_brief.json` |
| `soundscape_policy_build` | `understanding/soundscape_policy.json` (`cue_slots`) |
| `episode_structure_compose` | `understanding/episode_structure.json` |
| gate `g1_vo_pickup` | VO path readiness (`vo_path_ready`) |

Cousins: hollow compose/brief; Partial gate ladder; J-vo-ladder-partial; J-sdp-cue-slots (policy written here, consumed in sound/build).

### `plan_rank`

| Stage band | Role |
|------------|------|
| coverage → ranking | `topic_coverage_audit` … `full_master_ranking` → `master/selection.json` |
| sanitize / seat chain | `selection_order_sanitize` → … → `transitions` (MUST_PRECEDE spine) |
| nugget / gap recompose | `nugget_*` → `gap_report_sanitize` → `gap_framing_recompose` → `selection_framing_apply` |
| air contract | `air_script_*` → `air_contract_sanitize` → `transitions` |

Exit producer for sound: `transitions` (`master/transitions.json`). Seal gravity: `nugget_layup_compose` required for Phase-A seal (C-05). Cousins: J-phase-a-seal, J-freeze-constitution, hollow layup.

### `sound`

| Stage | Artifacts |
|-------|-----------|
| `sound_design_plan` | `understanding/sound_design_plan.json` |
| `vo_line_adjudicate` | `understanding/vo_line_adjudication.json` |

MUST_PRECEDE: `transitions` → SDP → adjudicate. Cousins: J-sdp-cue-slots; adjudicate hollow mid-batch.

### `build`

| Stage | Artifacts |
|-------|-----------|
| `vo_synthesize` | `mastering/vo_synthesize.json` + seated VO WAVs |
| `sound_design_vo_finalize` | SDP measures seated post-synth |
| `edl_narrative_audit` | `master/edl_narrative_audit.json` |
| `edl` | `master/edl.json` |
| `assembly_preview` | `master/assembly_preview.wav` |
| `listen_delight_audit` | `mastering/listen_delight_audit.json` |
| `music_palette_compose` / `sfx_prompt_craft` / `mmaudio_sfx` | palette + SFX (MUSIC_REQUIRES_ASSEMBLY) |
| `mix` | `master/assembly.wav` (must be `mix_outputs_seated`) |
| `junction_snip_qa` | `master/junction_snip_qa.json`, `master/seam_autopsy.json` |

Sole order exception vs seed: `junction_recut_precedes_mix` (MUST_PRECEDE lists only `edl` for junction). Cousins: J-mix-junction-precede, J-assembly-freshness, J-hollow-done, J-premature-pin.

### `ship`

| Stage | Artifacts |
|-------|-----------|
| `master_finalize` | `master/master.wav`, `master/post_master_quality.json` |
| `master_transcript_build` | `master/transcript.json` |
| `episode_meta_build` … `podcast_publish` | publish package tree |
| gate `g_publish` | operator Upload/Skip |

MUST_PRECEDE: `edl` → `master_finalize`. Ship filter also demands `committed_master_wav` for `SHIP_AFTER_MASTER`. Cousins: J-post-master-wait, J-hollow-done (false ship-ready).

---

## High-traffic MUST_PRECEDE edges

Source: `delivery_guardrails.MUST_PRECEDE` (23 consumers · **34** producer→consumer edges).  
`producer_ready(ctx, prod)` must be true before consumer enqueue/ask.

| # | producer → consumer | artifacts (producer authority) | ready meaning | freeze / ownership notes | cousin risk | linked junction |
|--:|---------------------|--------------------------------|---------------|--------------------------|-------------|-----------------|
| M1 | `selection_order_sanitize` → `air_script_compose` | `master/selection.json` | seed_complete | selection commit under freeze | freeze vs sanitize | J-freeze-constitution |
| M2 | `full_master_ranking` → `air_script_compose` | `master/selection.json` | seed_complete | ranking owns selection write | ranking↔TCA thrash | J-premature-pin |
| M3 | `information_package_plan` → `nugget_layup_compose` | package plan | seed_complete | layup incompleteness honest | hollow packages | J-hollow-done |
| M4 | `nugget_corpus_mine` → `nugget_layup_compose` | corpus | seed_complete | empty mine must not hollow-done | hollow corpus | J-hollow-done |
| M5 | `nugget_layup_compose` → `gap_report_sanitize` | `understanding/nugget_layup_plan.json` | seed_complete | **C-05 seal requires layup** | thin layup refuse seal | J-phase-a-seal |
| M6 | `gap_report_sanitize` → `refinement_agenda` | `understanding/gap_report.json` | seed_complete | gap writers vs End-A | freeze-skip gap writes | J-freeze-constitution |
| M7 | `gap_report_sanitize` → `gap_framing_recompose` | gap_report | seed_complete | same | same | J-freeze-constitution |
| M8 | `gap_framing_recompose` → `selection_framing_apply` | gap + selection | seed_complete | selection mutation gate | seat thrash | J-freeze-constitution |
| M9 | `selection_framing_apply` → `air_script_seams` | selection / air | seed_complete | air-order generation | order drift | J-assembly-freshness |
| M10 | `air_script_seams` → `air_contract_sanitize` | air script seams | seed_complete | mastering_plan vo_seats authority | omit under freeze | J-freeze-constitution |
| M11 | `air_contract_sanitize` → `transitions` | `mastering/mastering_plan.json` | seed_complete | End-A allowlist paperwork | dual freeze constitution | J-freeze-constitution |
| M12 | `nugget_layup_compose` → `transitions` | layup plan | seed_complete | dual producer for transitions | layup pin gravity | J-phase-a-seal |
| M13 | `transitions` → `sound_design_plan` | `master/transitions.json` | seed_complete | **phase_rank→sound cut** | optimizer SDP promote ungated | J-sdp-cue-slots · J-freeze-constitution |
| M14 | `sound_design_plan` → `vo_line_adjudicate` | `understanding/sound_design_plan.json` | seed_complete | cue_slots / dens | dens wipe beds | J-sdp-cue-slots |
| M15 | `vo_line_adjudicate` → `vo_synthesize` | `understanding/vo_line_adjudication.json` | seed_complete | **sound→build cut**; no mid-batch mark_done | hollow adjudicate | J-hollow-done · J-vo-ladder-partial |
| M16 | `vo_synthesize` → `sound_design_vo_finalize` | vo synth + WAVs | seed_complete | seated WAV demand | synth-fail unseat | J-vo-ladder-partial |
| M17 | `vo_synthesize` → `edl_narrative_audit` | heard VO | seed_complete | HE-1 heard VO not hollow | hollow audit | J-hollow-done |
| M18 | `sound_design_vo_finalize` → `edl_narrative_audit` | finalized SDP measures | seed_complete | post-synth seat | — | — |
| M19 | `edl_narrative_audit` → `edl` | `master/edl_narrative_audit.json` | seed_complete | narrative QC soft under Partial target | soft vs hard QC | — |
| M20 | `vo_synthesize` → `edl` | seated VO | seed_complete | EDL must not invent seats under freeze | freeze vs EDL rewrite | J-freeze-constitution |
| M21 | `edl` → `assembly_preview` | `master/edl.json` | seed_complete | EDL_CONSUMERS gate | hollow preview | J-hollow-done |
| M22 | `edl` → `listen_delight_audit` | edl | seed_complete | authoritative listen gate | delight pin / ESR cousins | J-post-master-wait |
| M23 | `assembly_preview` → `listen_delight_audit` | `master/assembly_preview.wav` | seed_complete | preview ≠ mix seat | freshness confuse | J-assembly-freshness |
| M24 | `edl` → `music_palette_compose` | edl | seed_complete | MUSIC_REQUIRES_ASSEMBLY | music-before-assembly | J-phase-a-seal |
| M25 | `listen_delight_audit` → `music_palette_compose` | delight audit | seed_complete | Phase A end (`PHASE_A_END`) | seal before music | J-phase-a-seal |
| M26 | `nugget_layup_compose` → `music_palette_compose` | layup | seed_complete | cross-phase producer | — | J-phase-a-seal |
| M27 | `vo_line_adjudicate` → `music_palette_compose` | adjudication | seed_complete | music after VO plan | adjudicate hollow → music thrash | J-hollow-done |
| M28 | `music_palette_compose` → `sfx_prompt_craft` | `sound_design/music_palette_compose.json` | seed_complete | Phase B | music epoch seal | J-phase-a-seal |
| M29 | `sound_design_plan` → `sfx_prompt_craft` | SDP | seed_complete | cross-band SDP | cue_slots | J-sdp-cue-slots |
| M30 | `sfx_prompt_craft` → `mmaudio_sfx` | `sound_design/sfx_prompts.json` | seed_complete | local MMAudio | stub WAV refuse epoch | — |
| M31 | `mmaudio_sfx` → `mix` | `sound_design/mmaudio_qa.json` | seed_complete | mix also needs edl | music incomplete → mix | — |
| M32 | `edl` → `mix` | edl | seed_complete | `mix_outputs_seated` completeness | assembly stale / generation | J-assembly-freshness · J-premature-pin |
| M33 | `edl` → `junction_snip_qa` | edl | seed_complete | **mix not required** when `junction_recut_precedes_mix` | multi-caller gate split | J-mix-junction-precede |
| M34 | `edl` → `master_finalize` | edl | seed_complete | also needs seated mix / junction honesty | hollow junction → false ship | J-hollow-done · J-post-master-wait |

---

## Row counts

| Section | Rows |
|---------|-----:|
| Phase boundaries (P1–P12) | 12 |
| MUST_PRECEDE edges (M1–M34) | 34 |
| **Total handoff rows** | **46** |

Critical Five stage inventory (for analysis packets, not extra ledger rows): fill_gaps 6+G1 · plan_rank 17 · sound 2 · build 11 · ship 7+G-Pub.
