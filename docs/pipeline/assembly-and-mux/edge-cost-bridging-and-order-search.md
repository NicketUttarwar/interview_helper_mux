---
id: mux-edge-cost-bridging
tier: high
status: spec
depends_on: [pipeline-assembly-mux]
---

# Edge cost, bridging, and order search

When assembly is more than **concat**, you need a **computable model of “bad joins”** between segments and a **search** that picks order and **small inserts** (room tone, music sting, micro silence) to minimize listener-visible seams—see stress cases in [../../execution/difficult-segment-combinations.md](../../execution/difficult-segment-combinations.md).

## Inputs

- Candidate segments with **acoustic features** (optional): RMS envelope, noise floor estimate, centroid.
- **Narrative tags** from scoring (topic, emotion coarse class, entities).
- **User constraints**: `force_include`, max duration, forbidden pairs ([../../execution/orchestration-component-map.md](../../execution/orchestration-component-map.md) archetype D).

## Edge cost (conceptual)

For each ordered pair `(i → j)`, combine:

- **Acoustic delta** (level, noise, ambience class mismatch).
- **Narrative risk** (non-monotonic time without signpost, contradiction flags, whiplash).
- **Processing mismatch** (denoised next to raw, S2S next to dry).

Costs are **not** universal constants; start **handcrafted**, optionally learn weights from past manual fixes ([../../cross-cutting/evaluation-metrics.md](../../cross-cutting/evaluation-metrics.md)).

## Search

- **Small N:** try permutations with pruning under duration budget.
- **Large N:** greedy + local swaps; or MIP/ILP if you formalize linear constraints.
- **Inserts:** finite catalog (e.g. 300 ms room pad, 2 s music bridge)—each insert is a **virtual segment** in the EDL ([timeline-and-edl.md](timeline-and-edl.md)).

## Relationship to other components

- **Does not replace** [dynamic-assembly-graph.md](dynamic-assembly-graph.md)—the graph says *what may follow what*; edge cost says *how painful each join is* and drives **ordering** within the graph.
- **Feeds** mastering: fewer fixes at final limiter if joins are smooth early.

## Open decisions

- Whether edge costs live in **manifest** (per interview) or **code defaults** only.

## Links

- [timeline-and-edl.md](timeline-and-edl.md)
- [../../execution/orchestration-component-map.md](../../execution/orchestration-component-map.md)
