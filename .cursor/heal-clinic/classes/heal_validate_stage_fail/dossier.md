# Heal clinic dossier — heal_validate_stage_fail

brain: 0.2.0 | mode_focus: partially_accelerated | all_modes_goal: true  
wave: implemented | L1_map: complete | L2_options: complete | verdict: decided B+ | L3_patch: implemented

## Plain-language card

- class_id: `heal_validate_stage_fail`
- plain name: Heal-validate then stage-fail
- what you’d notice in a run: Heal / flush / recovery says **ok / recovered / pass**, then the **same stage** (or the next one) fails again — identical loops, sticky thrash, or budget burn. It feels like the pipeline “fixed” something that never flipped.
- heal surfaces to census first (L1):
  1. Recovery `status=recovered` without proving the hole is gone
  2. Pre-flush / after-flush resilience soft-pass vs `mark_done`
  3. Pipeline re-runs failed stage on recover (ignores `resume_stage`)
  4. Identical-failure ledger skipped when falsely recovered
  5. Done Constitution / Admit plug-in (already shipped cousins)
- Partial Zero cousin families (HINT): SDP_CUE_SLOTS (heal-pass/stage-fail for cue slots — claimed closed); soft_pass refuse; HE-2 honest refuse pattern
- Stage Clinic overlap: soft-pass refuse / identical fingerprints (symptom, not this class SSOT)

## Evidence checklist

- [x] Caller census (recover / resilience / flush / identical)
- [x] Declared SSOT vs actual callers (`IN_CODE` tags)
- [x] Closed-on-HEAD vs residual (SDP cue closed; recovery/resilience residual)
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
L1 complete: census + permutations + residual + TEST_GAP in possibility.md.
