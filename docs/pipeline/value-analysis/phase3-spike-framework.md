# Phase 3 — Spike framework (rubrics, weights, aggregation)

Companion to [future-proofing.md](../../roadmap/future-proofing.md) and [value-metrics-library.md](./value-metrics-library.md). **Purpose:** score candidates so **winners maximize listener + idea + creator value**, not backwards compatibility.

## 1. Core principle: multiple weight profiles

No single weight vector. Run **2–3 profiles** per sprint and compare rankings. Sensitivity: perturb weights ±20%; if the winner swaps, document as **unstable ranking** and require human tie-break.

### 1.1 Named profiles

| Profile | Use when | Default intent |
|---------|----------|----------------|
| **Listener-first** | Broad consumer podcast | Max LEX-* |
| **Idea-first** | Technical / educational interview | Max COM-* |
| **Creator-first** | Solo operator throughput | Max CRE-* |
| **Moonshot-upside** | Portfolio of bets | Raise MOO-* |
| **Research purity** | Isolate signal quality | Raise MEC-A, de-emphasize product fit |
| **Production sobriety** | Late gate only | Raise MEC-D, MEC-C; not the research charter |

### 1.2 Example normalized weights (Outcome / Mechanism / Moonshot / SectionFit)

| Profile | w_out | w_mec | w_moo | w_sec | Notes |
|---------|-------|-------|-------|-------|-------|
| Listener-first | 0.60 | 0.25 | 0.10 | 0.05 | 60/25/10/5 style |
| Moonshot-upside | 0.50 | 0.20 | 0.25 | 0.05 | 50/20/25/5 |
| Idea-first (segmentation sprint) | 0.70 | 0.20 | 0.05 | 0.05 | Emphasize section fit + outcome |
| Creator-first | 0.45 | 0.20 | 0.10 | 0.25 | High section fit for editor tasks |
| Research purity | 0.35 | 0.45 | 0.15 | 0.05 | Mechanism-heavy |
| Equal | 0.25 | 0.25 | 0.25 | 0.25 | Sensitivity baseline |

Vectors must sum to 1.0 per profile.

## 2. Dimension set A — Outcome rubric (1–5 each)

| ID | Name | Definition |
|----|------|-------------|
| LEX-A | Attention sustain | Listener continues past first 60s / chapter |
| LEX-B | Sonic trust | Audio credible for the ideas (not polish for its own sake) |
| LEX-C | Emotional contour | Tension / release / warmth match story intent |
| COM-A | Concept carry | Post-listen: thesis + two supporting claims |
| COM-B | Distinction clarity | Listener repeats contrasts (A vs B) |
| COM-C | De-jargon success | Non-expert understands specialist terms in context |
| CRE-A | Option richness | More *good* editorial options, not noise |
| CRE-B | Decision latency | Time to confident decision decreases |
| CRE-C | Explainability | Operator states *why* a moment matters |

**Sub-vector:** `Outcome = mean(LEX-A,LEX-B,LEX-C,COM-A,COM-B,COM-C,CRE-A,CRE-B,CRE-C)` or weighted mean if a dimension is N/A for a candidate (document N/A).

## 3. Dimension set B — Mechanism rubric (1–5)

| ID | Name | Definition |
|----|------|-------------|
| MEC-A | Novel evidence channel | Uses signal absent from current first-class repo path |
| MEC-B | Composability | Feeds LLM stages as *features*, not duplicate narrative |
| MEC-C | Latency to value | Minutes to first useful artifact |
| MEC-D | Graceful degradation | Wrong outputs bounded harm to listener trust |

`Mechanism = mean(MEC-A..D)`.

## 4. Dimension set C — Moonshot rubric (1–5)

| ID | Name | Definition |
|----|------|-------------|
| MOO-A | Upside if right | Order-of-magnitude new modality or unlock |
| MOO-B | Reversibility | Easy feature-flag off |
| MOO-C | Learning spillover | Value even if hypothesis fails |

`Moonshot = mean(MOO-A..C)`.

## 5. Dimension set D — Section fit (1–5)

Use **one** section-local score per spike (pick the primary attachment section):

| Section | Local dimension | Prompt |
|---------|-----------------|--------|
| Segmentation | Boundary truth | Human: “cut here loses meaning?” |
| Gaps + VO | Comprehension risk | Blind listen without reading transcript |
| Flow 2 | Hook strength | First 3s + novelty vs other picks |
| Flow 1 narrative | Arc coherence | Blind preference on chapter order |
| Ingest / G0 | Trust alignment | Operator trusts queue ordering |
| Understanding | Role + beat alignment | Beats match perceived interaction |
| Sound + mix | Sonic intent fit | Sting/bed supports idea, not decoration |
| Orchestration | Long-run coherence | Memory spine reduces contradictions |

`SectionFit` = that single score.

## 6. Global aggregation

```
GlobalScore(profile) = w_out·Outcome + w_mec·Mechanism + w_moo·Moonshot + w_sec·SectionFit
```

- Compute per **candidate tool/method** per profile.
- Report **rank** per profile and **rank variance** (max rank − min rank across profiles).

## 7. Alternate weighting ideas (document in spikes)

1. **Pareto frontier** — plot (mean LEX, mean CRE); no scalar winner; pick from knee.
2. **Minimax** — maximize minimum dimension above a floor.
3. **Tiered veto** — hard fail if COM-A < 3 or LEX-B < 3; optimize remainder.
4. **Temporal discount** — multiply CRE-B by 1.2 for onboarding-sensitive spikes.

## 8. Spike modalities (evidence types)

| Modality | Feeds |
|----------|--------|
| Human listener study | LEX-*, COM-* |
| Operator timed task | CRE-* |
| Model proxy | MEC-A (document correlation risk) |
| Clip A/B | LEX-A, LEX-C |
| Retell protocol | COM-A, COM-B |

Minimum protocol detail lives in [value-metrics-library.md](./value-metrics-library.md).

## 9. Per-candidate spike record (required fields)

- Hypothesis ID(s), primary section, tier T0–T2.
- Scores: all applicable A/B/C/D dimensions (1–5).
- Scores per **profile** (at least Listener-first + one other).
- Evidence: clip timestamps, JSON paths, survey form link.
- **Verdict:** `Promote` | `Park` | `Kill` | `Merge` (with which ID).

Copy winners to [spike-results-and-winners.md](./spike-results-and-winners.md).

## 10. Templates

Blank tables: [spike-score-templates/](./spike-score-templates/).
