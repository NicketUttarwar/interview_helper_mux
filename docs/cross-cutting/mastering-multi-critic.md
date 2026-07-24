# Mastering multi-critic L4

Replaces the single L4 critique with an independent panel plus a flagship arbiter. Canon: [mastering-quality-hardening.md](./mastering-quality-hardening.md) · Engine: [mastering-shape-engine.md](./mastering-shape-engine.md).

**Problem:** one critic prompt produces correlated errors — it tends to like what the generator liked.

---

## Panel

Six critics run **in parallel**, each with its own minted prompt and its own evidence packet. No critic sees another critic's verdict.

| Critic id | Focus | Hard-fail power |
|-----------|-------|-----------------|
| `narrative_editor` | Arc coherence, information conveyance, clarity | no |
| `engagement_listener` | Hook strength, momentum, fatigue, impressiveness | no |
| `audio_intelligibility` | Masking, ducking, loudness swings, artifacts | no |
| `integrity` | Fabrication, misquote, false adjacency | **yes** |
| `pacing_repetition` | Density, dead air, repeated gestures | no |
| `style_fit` | Match to the per-run `eval_rubric.json` | no |

Only `integrity` can hard-fail a candidate on its own. Everything else feeds scoring.

---

## Score contract

Each critic returns, per candidate:

```json
{
  "candidate_id": "cand_2",
  "critic_id": "engagement_listener",
  "scores": { "hook_strength": 0.82, "fatigue_risk": 0.31 },
  "primary_dimension": "engagement",
  "verdict": "promote",
  "blocking": false,
  "issues": ["Hinge at 12:40 loses momentum"],
  "evidence_refs": ["mastering/auditions/cand_2/manifest.json#hinge"],
  "confidence": 0.74
}
```

`verdict` ∈ `promote` | `keep` | `demote` | `kill`. Scores are 0–1, higher is better, except explicitly named `*_risk` dimensions.

Critics must cite `evidence_refs`. A critic that cannot cite evidence for an issue must lower `confidence` rather than assert.

---

## Arbiter

Flagship. Input: all critic outputs + rubric + diversity/feasibility/integrity reports + audition manifests.

Responsibilities:

1. Reconcile disagreement without averaging away strong signals
2. Apply the per-run rubric weights ([`eval_rubric.json`](./mastering-quality-hardening.md))
3. Enforce hard kills from `integrity`
4. Produce per-candidate dimension vectors for [Pareto selection](./mastering-quality-hardening.md)
5. Emit deepen directives when the panel is split with low confidence

Output extends the existing L4 artifact `mastering/shape/cross_critique.json`:

- `critic_reports[]` — raw panel output
- `ranked_survivors[]` — with dimension vectors
- `killed[]` — with reasons and killing critic
- `deepen_directives[]`
- `arbiter_rationale`

---

## Disagreement policy

| Situation | Action |
|-----------|--------|
| Unanimous promote | Advance |
| Split, high confidence both sides | Keep both as Pareto candidates |
| Split, low confidence | Emit deepen directive (extra L3), max once per candidate |
| Integrity kill | Remove regardless of other scores |
| All candidates weak | Prefer simpler/sparser bespoke restraint over forced complexity |

---

## Cost

| Role | Tier |
|------|------|
| Six critics | standard |
| Arbiter | flagship |
| Deepen re-run | standard |

Config: `mastering.quality_hardening.critics.mode`, `.enabled_critics[]`, `.max_deepen_rounds`.

Prompts: `docs/prompts/mastering/critics/`.
