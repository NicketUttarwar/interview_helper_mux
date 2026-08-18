# Mastering quality eval corpus

Taxonomy and metrics: [../../../docs/cross-cutting/mastering-eval-corpus.md](../../../docs/cross-cutting/mastering-eval-corpus.md).

Each fixture directory holds:

- `fixture.json` — seven-axis tags plus the inputs (segments, speakers, assets, topology, candidates)
- `expectations.json` — what the hardening layer must conclude (routing hints, diversity floor, integrity landmines, false-positive traps, feasibility verdicts, **homunculus** conductor contracts)

Fixtures are JSON only. Audio-dependent behavior is asserted through manifests, not renders, so the suite stays offline and fast.

Coverage is enforced by `tests/test_mastering_quality_compilers.py::test_corpus_covers_every_axis_value` — if an axis value has no fixture, that test fails and the gap is the signal to add one.
