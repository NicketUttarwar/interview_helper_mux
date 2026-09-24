# Heal clinic dossier — post_heal_budget_thrash

brain: 0.2.0 | mode_focus: partially_accelerated | all_modes_goal: true  
wave: implemented | L1_map: complete | L2_options: complete | verdict: decided B+ | L3_patch: implemented

## Plain-language card

- class_id: `post_heal_budget_thrash`
- plain name: Budget thrash after “successful” heal
- what you’d notice in a run: Heal logged **recovered / ok**, then the same fingerprint still burns **identical×N**, **max_invokes**, **sticky heal**, **recovery budget_exhausted**, or **unstick loops**. It feels like “we fixed it” and then the run dies on budget.
- heal surfaces to census first (L1):
  1. Recovery R12c — every recovery log row (incl. `status=recovered`) mirrors into identical class counts
  2. Homunculus budget / ledger epochs — reclaim only on **product fingerprint flip**, not on heal success
  3. Sticky heal + thrash_report — no hook to `recovered`; unstick clears thrash **never** identical
  4. Pipeline / runtime resume after recovered → more stage starts toward dispatch caps
  5. BUD-1 product reclaim (closed) vs soak residual “same fp thrash after ok”
- Partial Zero cousin families (HINT): **BUDGET_THRASH** / **DP-BUD1** A implemented (fingerprint reclaim + refuse≠Finished); STEP_OFF named soak residual = thrash on **same** fingerprint — this class
- Stage Clinic overlap: identical×3 / sticky / max_invokes symptoms; root for this clinic is **post-success accounting**, not per-stage quality

## Evidence checklist

- [x] Caller census (who pins / resumes / mark_done / validate / **budget**)
- [x] Declared SSOT vs actual callers (`IN_CODE` tags)
- [x] Closed-on-HEAD vs residual (cousin_matrix / prior DPs — verify)
- [x] Partial vs Full-auto behavior split
- [x] Tests + TEST_GAP (`MUX_FORENSICS=0`)
- [x] OpenAI-assisted heal paths vs deterministic host rules (this class = host counters; LLM heal is upstream)

## Links

- Map: [possibility.md](possibility.md)
- Options: [options.md](options.md)
- Decisions: [decisions.md](decisions.md)
- Swarm: [solution_swarm/](solution_swarm/)

## Pack completeness

discovery_status: complete  
options_status: not_started  
Do not mark L1 complete without a filled possibility.md matrices — **filled**.
