# Mastering semantic integrity

Prevents the master from **fabricating meaning** out of real clips. Canon: [mastering-quality-hardening.md](./mastering-quality-hardening.md).

**Principle:** every clip can be authentic while the edit as a whole is a lie. Reordering, lifting, and VO framing are the risk surface.

Module: `src/interview_mux/mastering_semantic_integrity.py` · Artifact: `mastering/shape/semantic_integrity.json`

---

## Violation classes

| Class id | Severity | What it catches |
|----------|----------|-----------------|
| `quote_out_of_context` | critical | Hook lifts a clause whose meaning inverts without its neighbours (negation, conditional, hypothetical, quoting someone else) |
| `causality_reversal` | critical | Reorder makes an effect precede its stated cause |
| `false_reaction_adjacency` | critical | A reaction is placed against a statement it never responded to |
| `fabricated_exchange` | critical | VO + guest audio spliced to imply a conversation that never happened |
| `vo_overstates_claim` | critical | VO framing asserts more than the claim graph supports |
| `chronology_scramble` | warn | Narrative time jumps without a signposting bridge |
| `orphaned_referent` | warn | Retained clip references a removed antecedent ("that number", "as I said") |
| `reprise_implies_repeat` | warn | Hook segment replays later implying it was said twice |
| `attribution_drift` | warn | Speaker attribution ambiguous after reorder |

`critical` blocks the candidate in authoritative mode. `warn` becomes a repair directive attached to the candidate.

---

## Detection strategy

Hybrid — deterministic first, LLM only where language judgement is required.

### Deterministic signals

- **Context window check:** compare hook segment boundaries against sentence/clause boundaries from the transcript; flag mid-clause lifts.
- **Negation / conditional scan:** lexical markers (`not`, `never`, `if`, `unless`, `hypothetically`, `they claim`) inside or immediately before the lifted window.
- **Order inversion:** compare planned order against source timestamps; flag inversions crossing causal connectives (`because`, `so`, `therefore`, `that's why`).
- **Adjacency delta:** reaction turn placed against a statement more than N turns away in the source.
- **Referent scan:** anaphora (`that`, `it`, `those`, `he said`) whose antecedent segment is excluded.
- **Reprise detection:** same segment id in two timeline positions without `reprise_later`.

### LLM pass

A dedicated integrity critic reviews only the **flagged** windows plus the claim graph. It confirms or clears each deterministic flag and adds `vo_overstates_claim` judgements that lexical scans cannot make.

This keeps the LLM cost proportional to risk instead of scanning the whole transcript.

---

## Output

```json
{
  "version": 1,
  "candidates": [
    {
      "candidate_id": "cand_1",
      "verdict": "pass_with_warnings",
      "findings": [
        {
          "class_id": "orphaned_referent",
          "severity": "warn",
          "segment_id": "seg_22",
          "detail": "Opens with 'that number' — antecedent seg_21 excluded",
          "repair_directive": "Include seg_21, add a VO bridge, or drop seg_22",
          "source": "deterministic"
        }
      ]
    }
  ],
  "generated_at": "..."
}
```

---

## Repair, not just rejection

Every `warn` finding must carry a `repair_directive`. The Shape Engine may apply the repair (include antecedent, add bridge, drop clip) and re-run integrity once, rather than discarding an otherwise strong candidate.

`critical` findings are not repairable inside the same candidate — the plan must change.

---

## Relationship to invariants

This is the enforcement arm of the Mastering Process rule **never invent guest evidence**. The invariant forbids inventing words; semantic integrity forbids inventing *meaning*.

---

## Config

```
mastering.quality_hardening.semantic_integrity.mode              off|advisory|authoritative
mastering.quality_hardening.semantic_integrity.adjacency_max_turns  3
mastering.quality_hardening.semantic_integrity.llm_confirm       true
```
