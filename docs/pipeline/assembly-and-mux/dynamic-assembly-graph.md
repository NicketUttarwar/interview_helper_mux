---
id: mux-dynamic-graph
tier: high
status: idea
depends_on: [pipeline-assembly-mux]
---

# Dynamic assembly graph

Final master can be **data-dependent**: rules pick segment order or insert optional modules (intro, outro, “best of” block) based on scores or duration budget.

## Representation

- **DAG** or ordered list with **branches** resolved at render time.
- Each node outputs audio; edges define sequencing and mix policy.

## Open decisions

- Declarative rules engine vs embedded script for ordering.

## Links

- [../scoring-and-selection/diversity-constraints.md](../scoring-and-selection/diversity-constraints.md)
- [../../workflows/parallel-segmentation-candidates.md](../../workflows/parallel-segmentation-candidates.md)
- [../../execution/difficult-segment-combinations.md](../../execution/difficult-segment-combinations.md)
- [edge-cost-bridging-and-order-search.md](edge-cost-bridging-and-order-search.md)
