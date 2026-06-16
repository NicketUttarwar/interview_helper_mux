# Value map — cross orchestration + memory

## 1. Intent

Keep long interviews **coherent across passes**: investigations, memory, and reruns should reinforce the episode’s spine so operators and models do not fight each other.

## 2. Signals used today (context only)

`analysis_state.json`, investigation queue, orchestration loop per [analysis-orchestration-loop.md](../../../workflows/analysis-orchestration-loop.md).

## 3. Value hypotheses

| Hypothesis | One-line thesis |
|------------|-----------------|
| H-ORC-01 | **Chunked audio embeddings + summaries** build a hierarchical memory spine. |
| H-ORC-02 | **Acoustic anomaly + text ambiguity** jointly enqueue investigations. |
| H-ORC-03 | **Audio novelty + topic drift** composite flags long-run contradictions or missing callbacks. |

## 4. Listener / idea / creator

| ID | LEX | COM | CRE |
|----|-----|-----|-----|
| H-ORC-01 | ○ | ● | ● |
| H-ORC-02 | ○ | ● | ● |
| H-ORC-03 | ● | ● | ○ |

## 5. Moonshot tier

| ID | Tier |
|----|------|
| H-ORC-01 | T1 |
| H-ORC-02 | T1 |
| H-ORC-03 | T2 |

## 6. Spike artifacts

- Trace: investigations fired with/without acoustic trigger; operator rates helpfulness.
- Long interview fixture (**30m+**) with planted contradiction — `tests/fixtures/runs/coherence_30m_planted_drift/`.
- Artifact: `understanding/coherence_report.json` — see [coherence-orc03.md](../../../cross-cutting/coherence-orc03.md).

## 7. Spike winner (fixture sprint)

**Promote:** H-ORC-01 interview comprehension spine — shipped as `interview_spine_build` ([interview-spine.md](../../../cross-cutting/interview-spine.md)). **Promote:** H-ORC-02 acoustic anomaly + text ambiguity investigation queue — [spike-results § orchestration](../spike-results-and-winners.md#cross-orchestration-memory). Fixture: `tests/fixtures/value_analysis/spike_cross_orchestration_memory.json`. Tool direction: [tools-not-in-repo § Lever E — anomaly triggers](../tools-not-in-repo-landscape.md#lever-e--long-run-coherence-memory).

## Related

- [future-proofing.md](../../../roadmap/future-proofing.md)
- [long-interview-chunking.md](../../../workflows/long-interview-chunking.md)
- [spike-results-and-winners.md](../spike-results-and-winners.md#cross-orchestration-memory)
