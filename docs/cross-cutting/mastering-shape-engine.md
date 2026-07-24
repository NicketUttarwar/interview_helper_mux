# Mastering Shape Composition Engine

Detail for the Mastering Process shape lane. Canon: [mastering-process.md](./mastering-process.md). Construction decisions: [mastering-construction-decisions.md](./mastering-construction-decisions.md). Reliability gates: [mastering-quality-hardening.md](./mastering-quality-hardening.md).

---

## Purpose

Semi-autonomous, **per-podcast** analysis that invents its own agenda, mints and **edits** system prompts, and adjusts depth until the **best bespoke** `mastering_plan.json` emerges. Fixed capability modules are scheduled tools — not a rigid pipeline.

---

## North-star & pillars

Same as [mastering-process.md](./mastering-process.md): best listener outcome; promote excellence; filter ruthlessly; bespoke not programmatic; non-repetitive; best ensemble; convey real knowledge; impressive when earned.

L4 is the **primary excellence filter**. All levels share the pillars via minted system instructions.

---

## Flow

```
research_dossier (routed + evidence-packed)
  → L0 Meta-architect → shape/agenda.json + shape/eval_rubric.json
  → L1 Horizon → L2 Candidates
  → diversity → feasibility → semantic integrity → micro-render auditions
  → L4 multi-critic panel + flagship arbiter → Pareto frontier → L5 Convergence
  → (prompt mint/edit + capability modules interleaved)
  → Flagship synthesize → mastering_plan.json
```

L3 Deep dive is inserted adaptively by the agenda and by arbiter deepen directives.

---

## L0 — Meta-architect

**Tier:** flagship (first agenda); economy for micro-updates.

**Input:** full `research_dossier`.  
**Output:** `mastering/shape/agenda.json` **and** `mastering/shape/eval_rubric.json` (style axes + weighted criteria + anti-patterns for *this* source — every critic and the polish audit score against it).

Must include:

- Levels to run / skip / deepen for *this* source
- Ordered **custom steps** unique to this podcast
- Per-step seed goals oriented to *best final listen* (not checklist coverage)
- Initial system-prompt drafts with north-star pillars
- Anti-patterns to hunt (e.g. “dense Q&A — avoid bed wallpaper”)
- Budgets: `max_steps`, `max_prompt_edits`, `max_flagship_calls`, tier hints

Every podcast gets a **different agenda**. No global fixed shape checklist.

---

## L1–L5 — Adaptive depth

| Level | Role | Tier | When |
|-------|------|------|------|
| L1 Horizon | Exceptional vs generic risks; flag anti-patterns | economy | Always |
| L2 Candidates | Competitive shape + cold-open hypotheses; each claims why *best* | standard | Always |
| L3 Deep dive | Strengthen winners; kill weak with evidence | standard; flagship on conflict | Low confidence, near-clone candidates, or agenda “deep” |
| L4 Cross-critique | Excellence filter (below) | standard; flagship if top-2 tied | ≥2 candidates, soft-pass, or templated look |
| L5 Convergence | Survivors → pre-synthesize brief arguing one bespoke architecture | standard | Always before synthesize |

Depth adjusts dynamically (insert L3, remint, skip). Cap via agenda budget.

### L4 excellence filter (required behaviors)

1. Score: listener impact, information clarity, bespoke fit, ensemble quality, non-repetition, cold-open strength, SFX restraint, programmatic risk
2. Promote top candidate(s) with evidence refs
3. Filter “valid but dull / repetitive / template / stuffed”
4. Demand differentiation — or prefer simpler sparse/`none` over forced complexity
5. Ensemble check: open + body + VO/SFX + close as one custom solution
6. Invariant gate: pickup voice; no invented guest speech; locked speaker volleys
7. Output: `mastering/shape/cross_critique.json` (ranked survivors, killed + reasons, optional deepen directives)

L4 runs as a **six-critic panel plus flagship arbiter**, scoring against the per-run rubric and the audition manifests — see [mastering-multi-critic.md](./mastering-multi-critic.md). Survivors are then kept on a Pareto frontier instead of collapsed to one aggregate score.

### Hardening gates around L2–L4

| Order | Gate | Effect |
|-------|------|--------|
| after L2 | [diversity](./mastering-quality-hardening.md) | Near-clone candidates forced to remint |
| then | [feasibility](./mastering-feasibility.md) | Unbuildable candidates removed before any spend |
| then | [semantic integrity](./mastering-semantic-integrity.md) | Critical fabrications removed; warnings become repair directives |
| then | [auditions](./mastering-audition-loop.md) | Top survivors rendered as 30–90 s excerpts |
| L4 | multi-critic + arbiter | Panel scores plans **and** rendered audio features |
| after L4 | Pareto | Frontier survivors, not a single winner, feed synthesize |

---

## Prompt mint and edit

1. Mint → `mastering/prompts_minted/shape/{step_id}.vN.system.txt` (pillars embedded)
2. Run multi-turn volley
3. Critique: “pushing best bespoke outcome, or generic completeness?”
4. Edit → `vN+1` + `prompt_edit_log` entry
5. Re-run until acceptance or edit budget exhausted

**Promotion gate:** edits are **run-local** by default. A minted/edited prompt becomes a global seed only after it passes the [eval corpus](./mastering-eval-corpus.md) thresholds *and* an operator approval artifact. Config: `mastering.prompt_edit.allow_global_promotion` (default `false`).

---

## Semi-autonomous loop

```
while agenda has next step and budget remains:
  mint/edit system prompt (pillars always present)
  run LLM volley
  evaluate acceptance + excellence score
  clarify → auto-resolve else operator (capped)
  deepen → insert follow-up (economy micro-update)
  schedule capability module if needed
  if L4 leaves only weak options → prefer bespoke restraint
  advance
```

Operator interrupts: unresolved clarifying questions or hard invariant failures only.

---

## Capability modules

| Module | Artifact | Job |
|--------|----------|-----|
| `cold_open_hook` | `shape/cold_open_hook.json` | Dynamic open (none / segment / VO clone / VO+segment ± SFX) |
| `structure_candidates` | `shape/structure_candidates.json` | Competitive bespoke shapes |
| `inclusion_exclusion` | `shape/inclusion_exclusion.json` | Focus / exclude / reorder |
| `pacing_density` | `shape/pacing_density.json` | Duration / density / silence |
| `vo_sfx_components` | `shape/vo_sfx_components.json` | VO/SFX/transition mix |

Engine decides when/how deep. Soft-pass with gaps OK; hard fail only on invariants.

---

## Flagship synthesize

**Input:** dossier + agenda + rubric + level reports + module outputs + prompt_edit_log + L4 arbiter output + Pareto frontier + audition manifests.  
**Output:** `mastering/mastering_plan.json` — sole Realization intent.  
Must choose among **frontier survivors** and argue why this is the **best bespoke** construction (not merely valid), naming the tradeoff it accepted in `bespoke_rationale`.

---

## OpenAI cost routing

| Role | Tier |
|------|------|
| Mint / edit / acceptance / clarify / agenda micro-update | economy |
| L1, most L3, L4 default, capability modules | standard |
| L0 first agenda, L3 escalate, L4 tie-break, synthesize, polish audit | flagship |

Planned config: `mastering.shape_engine.budgets.max_steps`, `max_prompt_edits`, `max_flagship_calls`, `tiers.*`.

---

## Hard invariants

- New VO → pickup-eligible speaker only
- Never invent guest evidence
- Cannot schedule a step that violates the above
- Cannot synthesize a plan built from an infeasible or critically non-integral candidate
- Cannot select a `vo_clone_*` open without recorded clone consent ([mastering-voice-clone-policy.md](./mastering-voice-clone-policy.md))
