# Defaults inventory — Full-auto + Partial on HEAD

last_verified: 2026-09-19  
brain: 0.2.0  
mode: full_auto + partially_accelerated  
code_is_king: true

Each row: key/behavior | default value | code site | **full_auto** | **partial_auto** | **must_act_partial**

## Start / run posture

- brain id (`latest` → highest registered = **0.2.0**): `config/app.defaults.json` → `mastering.homunculus.default_version` = `"latest"` | `homunculus/version.py` registry | FA: seed walk | PA: seed walk | must_act: Start choice
- pipeline mode Full-auto: GUI Start / `run_mode=full-auto` | `web/server.py` + `full_auto_launch.py` | FA: detached driver | PA: n/a | —
- pipeline mode Partial: GUI Start / `run_mode=partially-accelerated` | `automation_run` + driver | FA: n/a | PA: prepare-until-G0 then continue | must_act: **G0**
- `homunculus.mode`: `"authoritative"` | app.defaults | packing/admit rails on | same | —
- podcast destination: operator-selected at Start (not auto) | both | must_act: Start

## Gate & auto-accept

- `analysis.gap_fill.auto_accept_defaults`: **false** | app.defaults | FA: env/driver may OR | PA: no nested auto-stamp | framing/pickup/voice-ref when ladder open
- `INTERVIEW_MUX_AUTO_ACCEPT_GATES=1`: env OR with the flag above | `gap_vo_gates.auto_accept_gap_gate_defaults_enabled` | FA: drivers set | PA: typically unset | —
- Homunculus **0.2.0** G-Framing path: `recommended_framing_action` → `auto_resolve` Yes for hosted when unset | `homunculus/gates.py` + `maybe_auto_accept_gap_gate_defaults` | FA: may proceed | PA: still operator for honest pickup | G-Framing when pending
- **B1 applied:** Full-auto meta (`run_mode=full-auto` / `full_auto=true`) + recommended `auto_resolve` also arms that path even when `has_homunculus_features` is false (brain 0.0.0) and env/config auto-accept are off | `gap_vo_gates.maybe_auto_accept_gap_gate_defaults`
- **B3 KEEP:** `analysis.gap_fill.auto_skip_when_ineligible=false` (loud fail when Yes+ineligible); do not flip to silent skip | app.defaults + `gap_fill_eligibility`
- G0 (`transcript_review`): body does not auto-close; Full-auto driver must `complete_g0` | `transcript_review_build` + driver | FA: driver | PA: **must_act** | **yes**
- `OPERATOR_GATE_STAGES`: transcript_review(_build), topic_coverage_audit (voice-ref reasons), delivery_epoch_unlock, podcast_publish | `operator_gates.py` | FA: auto-clear where coded | PA: journey pauses | G0 / G-Publish / unlock when armed
- `should_stamp_needs_operator`: see Wave 2 — 0.2.0 early-return footgun inventory below

## Unattended stall policy

- Must route via classified remediation (not permanent operator): VO contract/coverage, stale upstream, seed order, layup/selection drift markers, **junction osc/budget exhaust** | `AUTOMATED_CLASSIFIED_MARKERS` + playbooks | heal ladder then refuse terminate
- Sanitize refused / unsanitary selection/gap/air/sdp: still hard stamp | `should_stamp_needs_operator` | halt
- Preclean: **ruled (Q6A)** — Full-auto may `auto_run_before_ingest=true`; docs aligned in operator-gates.md. Partial prepare-until-G0 still defers. | audio_preclean | was landmine; closed |

## Quality / ship defaults

- `listen_delight.mode`: **authoritative** | app.defaults | ship bar at finalize (fail_early_at_audit_stage: **false**)
- `listen_delight.fail_early_at_audit_stage`: false | pre-mix advisory; block at master_finalize
- `listen_delight.max_remutate_attempts`: **3** | app.defaults | finite remutate budget then ship-best / refuse (sticky exhaust; recovery budget aligned)
- Aspirational quality / remutate: pick-best after N remutate attempts (`aspirational_quality.max_attempts_per_family` still 3 for family ledger)
- `e2e_soft` / soft-ship: Full-auto Start enables soft e2e path per operator-gates.md | full_auto_launch | logged decisions
- G-Listen: config `sound_design.g_listen_mode` default **warn** (advisory, non-blocking) | remaster/mix can arm pending | **Full-auto** auto-clears when mode is block|block_mix via `gates.maybe_auto_clear_g_listen_for_full_auto`; **Partial** under defaults = warn (no finalize stall); block only if operator sets `block`/`block_mix`
- Narrative QC: `narrative_qc.strict` softened via `is_unattended_run` (Full-auto **and** Partial) | `gates.check_narrative_qc` | intentional progress posture; Manual stays strict
- Delivery unlock: structural archive blocked until unlock | air-order / delivery_epoch | Full-auto must avoid unnecessary locks or auto-path; Partial must-act when locked

## Partial Phase-0 must-act (compact)

| Gate | When | must_act_partial |
|------|------|------------------|
| G0 | After `transcript_review_build` | **yes** |
| G-Framing / pickup / voice-ref / clone | Ladder open | **yes** (nested synth skip-not-stamp) |
| G1 | After gap stages | optional |
| Preclean | Checkpoint offer | never auto on Partial prep |
| G-Listen | After mix when recommended | **no** under defaults (warn) |
| G-Publish | After master transcript | **yes** when armed |

## Offers that must not block

- Preclean offer vs actual auto_run — CODE_DOC_CONFLICT risk (map: audio_preclean)
- Optional G1 skip: unattended Chatterbox path should stay automation_pending | HV-5 tests historically on 0.1.0 meta
- Write-approval: auto-commit in v2 | removed gate

## Stage-local landmines (from Wave 1 maps)

| stage_id | flag/behavior | default | code site | full_auto | partial_auto | must_act_partial |
|----------|---------------|---------|-----------|-----------|--------------|------------------|
| audio_preclean | skip vs isolated.wav incompleteness | auto_run conflict | stage_completion / preclean | may auto | defer prep | checkpoint offer |
| low_conf_island_scan | enabled=false early return | often off | low_conf stage | HIGH pending | HIGH | — |
| interview_spine_build | enabled=false skip stub + heal; KEEP in seed (4B ISB-B1) | enabled=true default | `interview_spine_stage` | LOW | LOW | — |
| air_script_compose | enable=false skip latch + heal (ASC-B2); ASC-B3 omits leave selection alone | enable=true | air_script | LOW | LOW | — |
| air_script_seams | enable=false skip latch + heal (ASS-B2); ASS-B3 KEEP soft-freeze no-op | enable=true | air_script / seat_authority | LOW | LOW | — |
| episode_meta_build | EMB-B1 refuse empty/Untitled title (no hollow done) | OpenAI title required | `podcast_publish._persist_meta` | MED | MED | — |
| sfx_prompt_craft | g1_5_require_prompt_approval=true; Full-auto auto-approves | true | `sfx_prompt_review` | LOW | MED GUI | when warnings |
| mix / junction_snip_qa | thrash / incomplete_cut | max_mix_cycles=3 | agenda + junction | HIGH | HIGH | — |
| mix | g_listen after successful mix/remaster | default **warn** | `sound_design` → `maybe_auto_clear_g_listen_for_full_auto` | LOW | LOW (warn) | no under defaults |
| master_finalize | delight authoritative + g_listen | default **warn** | `require_g_listen_clear` | LOW | LOW (warn); HIGH if block | no under defaults |
| podcast_publish | skip hollow / S3 advisory consent | DONE-local refuse-remote | publish / sync_assets | MED local | HIGH until Upload/Skip | **yes** G-Publish |
| junction_snip_qa | osc/budget exhaust | classified refuse terminate | junction / thrash / operator_gates | LOW | LOW | — |
| master_finalize | aspirational advisory ship | Advisory = local ship OK | aspirational_quality + listen_delight | LOW local | LOW local | — |
| listen_delight_audit | fail_early + ship re-run | KEEP `fail_early_at_audit_stage=false` | listen_delight + master_finalize | LOW | LOW | — |
| transitions | empty transitions | min_rows 0 KEEP empty OK | contract sufficiency | LOW | LOW | — |
| mmaudio_sfx | omit-all reserved themes | NOT ship-legal under creative_delivery | theme_slot_integrity + listen_delight | HIGH | HIGH | — |
| framing / missing_framing | `auto_accept_defaults`; **KEEP** `auto_skip_when_ineligible=false` | `gap_vo_gates` + `homunculus/gates` | LOW FA | MED without clone | G-Framing / consent when open |
| full_master_ranking | `narrative_qc.strict` softened under unattended (X-3) | `gates.check_narrative_qc` | LOW | LOW (soft) | no |
| refinement_agenda | RA-B2: present dirty gap blocks agenda | `refinement_agenda._gap_unsanitary_block` | MED | MED | — |
| gap_framing_recompose | GFR-B3: non-layup activate retired → skip-copy | `refinement_passes.run_gap_framing_recompose` | LOW | LOW | — |
| transcribe | non-ARM or missing `ASSETS/local_speech`; empty words KEEP done (4B) | hard RuntimeError on env | `transcribe_local.run_transcribe` | HIGH env | HIGH env | — |
| audio_probe_build | fail_open empty artifacts KEEP (4B) | `audio_probes.fail_open=true` | audio_probes | LOW | LOW | — |
| gap_framing_compose | framing Yes + zero/hollow lines → incomplete (Q2A CSP-05) | framing Yes | `gaps.run_gap_framing_compose` | MED | MED | — |
| mastering_shape_agenda | rubric LLM fail → incomplete (Q2A CSP-05); soft_gate on | **shape.llm=true** | `run_mastering_shape_agenda` | MED | MED | — |
| topic_coverage_audit | soft-fail LLM → incomplete/refuse (Q2A CSP-05) | soft_progression | `run_topic_coverage` | MED | MED | — |
| source_topology_build | mid-seed pickup auto removed (STB-B3) | `auto_accept_defaults=false` | `gap_vo_gates.maybe_auto_accept_gap_gate_defaults` | MED | MED | pickup confirm |
| ideal_cuts_propose | long-tape span floor + OpenAI ≤2; enable default true | `min_span_coverage_ratio=0.45` | `run_ideal_cuts_propose` | MED | MED | — |
| boundary_detection | skip LLM when ideal-cuts bind quality OK — **KEEP** (5A) | `skip_boundary_llm_when_bound=true` | `run_boundaries` | MED | MED | — |
| edl nested synth | Partial never auto-stamps VO ladder; skip mint when open | `nested_synth_may_mint` | LOW FA | skip-not-stamp | G1 / vo_synthesize |
| segment_classification | det skip when bound — **KEEP** (5A); else OpenAI (±shards) | `skip_classification_llm_when_bound=true` | `run_classification` + `try_deterministic_classification` | MED (batch incomplete hard-fail; resplit unlink) |
| content_brief_reanchor | OpenAI overwrite shared brief; completeness required | thesis/topics sufficiency blocking | `run_content_brief_reanchor` | MED (hollow persist refuse; resplit re-entry) |
| vernacular_segment_sanitize | fail_open skip/resplit; HS-5 report honesty | `audio_probes.fail_open=true` | `run_vernacular_segment_sanitize` | MED (write-fail limbo; contract hard boundaries lie) |
| connector_fuse_pass | economy seam LLM + finite caps; HS-3 skip stubs | `enabled=true`; **`max_*=0` → runtime 24/8** (not unlimited); incomplete_thought_only | `resolve_fuse_round_caps` / `run_connector_fuse_pass` | HIGH (oscillation / over-invalidate) |
| sound_design_palettes | deferred empty palettes on Full-auto | **`early_palettes_llm=false`** (shipped) | `run_sound_design_palettes` + completeness deferred_ok | MED (contract sufficiency was overclaiming min≥1) |
| mastering_research_routing | stub when LLM off; llm_failed refuse when on+fail (Q2A CSP-05) | **`mastering.research.llm.enabled=false`** | `run_research_routing` | LOW (default off; refuse only when llm on) |
| mastering_research_rollup | A-01 shape-core thin pins Shape/gap (not soft-done) | research.llm off; dual dossier/rollup write | `_persist_research_dossier` + `_research_thin_late_refuse` | MED (thin delays Shape under Full-auto — intentional) |
| information_package_plan | mode commits packages onto plan (not shadow) | **`commit_music_vo`** (enable=true) | `information_packages.py` + app.defaults | LOW unattended; IPP-B2 empty corpus → incomplete |
| vo_line_adjudicate | coverage shortfall warn+continue; VO text hard-gate | **`adjudicate_fail_open=true`** + synthesize VO comprehensibility hard fail (Q1A+) | `adjudicate_cfg` + `synthesize_vo_comprehensibility_errors` | MED (junk VO stops; thin coverage continues) |
| vo_synthesize | Full-auto record-required lines | rewrite → `delivery=synthesize` | `rewrite_full_auto_record_lines_to_synth` | LOW unattended; partial-auto still hard_blocks record (HV-5) |

## Wave 2 fix priority (unambiguous)

1. `should_stamp_needs_operator` must apply classified allowlist on **0.2.0** unattended (not early-return True for all non-0.1 versions) — DoD #3
2. Disabled stages that return without skip artifact / heal must not leave seed pending — CSP-01 ruled for low_conf + air_script (ASC-B2/ASS-B2) + spine ISB-B2 — DoD #1/#2
