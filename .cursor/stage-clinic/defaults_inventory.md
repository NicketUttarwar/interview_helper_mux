# Defaults inventory — Full-auto on HEAD

last_verified: 2026-09-17  
brain: 0.2.0  
mode: full_auto  
code_is_king: true

Each row: key/behavior | default value | code site | unattended effect

## Start / run posture

- brain id (`latest` → highest registered = **0.2.0**): `config/app.defaults.json` → `mastering.homunculus.default_version` = `"latest"` | `homunculus/version.py` registry | new runs get seed walk
- pipeline mode Full-auto: GUI Start / `run_mode=full-auto` | `web/server.py` + `full_auto_launch.py` | sets `meta.full_auto`, launches detached driver
- `homunculus.mode`: `"authoritative"` | app.defaults | packing/admit rails on
- podcast destination: operator-selected at Start (not auto)

## Gate & auto-accept

- `analysis.gap_fill.auto_accept_defaults`: **false** | app.defaults | G-Framing not accepted via this flag alone
- G-Framing under 0.2.0 Full-auto: homunculus auto-resolve Yes for hosted 1:1 when unset | `mastering-homunculus.md` + gate closers | unattended can proceed without GUI Yes
- G0 (`transcript_review`): body does not auto-close; Full-auto driver must `complete_g0` | `transcript_review_build` + driver | stall if driver skips
- `OPERATOR_GATE_STAGES`: transcript_review(_build), topic_coverage_audit (voice-ref reasons), delivery_epoch_unlock, podcast_publish | `operator_gates.py` | journey pauses
- `should_stamp_needs_operator`: see Wave 2 — 0.2.0 early-return footgun inventory below

## Unattended stall policy

- Must route via classified remediation (not permanent operator): VO contract/coverage, stale upstream, seed order, layup/selection drift markers | `AUTOMATED_CLASSIFIED_MARKERS` + playbooks | heal ladder
- Sanitize refused / unsanitary selection/gap/air/sdp: still hard stamp | `should_stamp_needs_operator` | halt
- Preclean: offer “never auto-run” vs `auto_run_before_ingest` default — verify in code before Full-auto assumptions | audio_preclean | landmine

## Quality / ship defaults

- `listen_delight.mode`: **authoritative** | app.defaults | ship bar at finalize (fail_early_at_audit_stage: **false**)
- `listen_delight.fail_early_at_audit_stage`: false | pre-mix advisory; block at master_finalize
- Aspirational quality / remutate: see mastering config (pick-best after attempts)
- `e2e_soft` / soft-ship: Full-auto Start enables soft e2e path per operator-gates.md | full_auto_launch | logged decisions
- G-Listen: config `sound_design.g_listen_mode` (warn vs block) | remaster can arm pending | block stalls finalize if mode=block
- Delivery unlock: structural archive blocked until unlock | air-order / delivery_epoch | Full-auto must avoid unnecessary locks or auto-path

## Offers that must not block

- Preclean offer vs actual auto_run — CODE_DOC_CONFLICT risk (map: audio_preclean)
- Optional G1 skip: unattended Chatterbox path should stay automation_pending | HV-5 tests historically on 0.1.0 meta
- Write-approval: auto-commit in v2 | removed gate

## Stage-local landmines (from Wave 1 maps)

| stage_id | flag/behavior | default | code site | stall risk |
|----------|---------------|---------|-----------|------------|
| audio_preclean | skip vs isolated.wav incompleteness | auto_run conflict | stage_completion / preclean | HIGH |
| low_conf_island_scan | enabled=false early return | often off | low_conf stage | HIGH pending stall |
| interview_spine_build | enabled=false refuse heal | | spine | HIGH |
| air_script_compose | enable=false unmarked | | air_script | HIGH |
| sfx_prompt_craft | g1_5_require_prompt_approval | check HEAD | sfx | HIGH if true |
| mix / junction_snip_qa | thrash / incomplete_cut | max_mix_cycles=3 | agenda + junction | HIGH |
| master_finalize | delight authoritative + g_listen block | | finalize | HIGH |
| podcast_publish | skip hollow / S3 advisory consent | | publish | HIGH |
| framing / missing_framing | auto_accept_defaults false; rely 0.2.0 auto | | gap_fill | MED |
| transcribe | non-ARM or missing `ASSETS/local_speech` | hard RuntimeError | `transcribe_local.run_transcribe` | HIGH (env prerequisite) |
| source_topology_build | pickup confirm at stage end is no-op; real confirm at framing | `auto_accept_defaults=false`; Full-auto driver sets env | `maybe_auto_confirm_pickup_speaker` vs `maybe_auto_accept_gap_gate_defaults` | MED (stall if neither env nor homunculus) |
| ideal_cuts_propose | long-tape span floor + OpenAI ≤2; enable default true | `min_span_coverage_ratio=0.45`; `enable=true` | `run_ideal_cuts_propose` + `llm_simple` persist retry | MED (span refuse after budget) |

## Wave 2 fix priority (unambiguous)

1. `should_stamp_needs_operator` must apply classified allowlist on **0.2.0** unattended (not early-return True for all non-0.1 versions) — DoD #3
2. Disabled stages that return without skip artifact / heal must not leave seed pending (low_conf, air_script enable=false patterns) — DoD #1/#2
