# Value map — shared gaps + VO (missing framing + optimal questions)

## 1. Intent

Detect where a **listener** would lose the thread and propose **minimal** interviewer speech that restores comprehension—without stealing the guest’s ideas.

## 2. Signals used today (context only)

LLM `missing_framing` and `optimal_questions`; outputs include `gap_report.json` and interviewer script per [logic-tree.md](../../../logic-tree.md).

## 3. Value hypotheses

| Hypothesis | One-line thesis |
|------------|-----------------|
| H-GAP-01 | **Blind listener comprehension risk** scores segments without blaming a specific STT vendor. |
| H-GAP-02 | **Speaking rate + pause structure** proxy cognitive load for gap severity. |
| H-GAP-03 | Rank VO line candidates by **predicted COM uplift** (retell A/B). |

## 4. Listener / idea / creator

| ID | LEX | COM | CRE |
|----|-----|-----|-----|
| H-GAP-01 | ● | ● | ○ |
| H-GAP-02 | ● | ● | ● |
| H-GAP-03 | ○ | ● | ● |

## 5. Moonshot tier

| ID | Tier |
|----|------|
| H-GAP-01 | T0 |
| H-GAP-02 | T1 |
| H-GAP-03 | T1 |

## 6. Spike artifacts

- Retell scores with/without proposed VO line.
- Comprehension risk sheet per segment window.

## Related

- [future-proofing.md](../../../roadmap/future-proofing.md)
- [interviewer-gap/README.md](../../interviewer-gap/README.md)
