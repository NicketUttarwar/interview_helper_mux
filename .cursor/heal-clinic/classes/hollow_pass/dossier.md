# Heal clinic dossier — hollow_pass

brain: 0.2.0 | mode_focus: partially_accelerated | all_modes_goal: true  
wave: analysis | L1_map: complete | L2_options: not_started | verdict: none | L3_patch: not_started

## Plain-language card

- class_id: `hollow_pass`
- plain name: Hollow pass
- what you’d notice in a run: A stage shows **done** / seed walks past it / MUST_PRECEDE treats a producer as **ready**, but the real primary JSON/WAV is missing, thin, refuse-stub, or never seated — later thrash, wrong pin, or ship lies.
- heal surfaces to census first (L1):
  1. `RunContext.mark_done` / `is_done` / `.stage_done` writers
  2. Done Authority (`try_mark_done`, `is_seed_complete`, finalize PMQ)
  3. `seed_stage_complete` / `producer_ready` / `stage_outputs_present` / `stage_artifact_incompleteness`
  4. Heal restamp (`apply_seed_order_heal`) + orphan promote / hollow unmark (G3)
  5. `heal_or_refuse_mark` + `_mark_done_raw` escapes
- Partial Zero cousin families (HINT): `HOLLOW_DONE` (cousin_matrix claims closed via DP-DONE-AUTHORITY) · `J-hollow-done` · XC-HOLLOW-01 · Stage Clinic HV3/HV4/HF1 hollow series
- Stage Clinic overlap: `vo_line_adjudicate` (HV3), `vo_synthesize` / G1 skip (HV4), pass-2 hollow (HF1), mix unseated (HX2), ship finalize (HPUB*), SAP/topology/G0 build hollow (HU*/HP*)

## Evidence checklist

- [x] Caller census (mark_done / seed-complete / restamp / unmark / promote)
- [x] Declared SSOT vs actual callers (`IN_CODE` tags)
- [x] Closed-on-HEAD vs residual (cousin_matrix HOLLOW_DONE + leapfrog B+ VO honesty — verify)
- [x] Partial vs Full-auto behavior split
- [x] Tests + TEST_GAP (`MUX_FORENSICS=0`)
- [x] OpenAI-assisted heal paths vs deterministic host rules

## Links

- Map: [possibility.md](possibility.md)
- Options: [options.md](options.md)
- Decisions: [decisions.md](decisions.md)
- Swarm: [solution_swarm/](solution_swarm/)

## Pack completeness

discovery_status: complete  
options_status: not_started  
L1 complete: census + permutations + residual + TEST_GAP written in possibility.md.
