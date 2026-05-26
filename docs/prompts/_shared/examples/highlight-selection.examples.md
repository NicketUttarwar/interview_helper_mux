# highlight-selection examples (reference)

**Good — diverse picks**

- Five clips across different `topic_tags`; `scores.diversity_bonus` high on later picks; `rejected_candidates` lists ≥3 with reasons like `redundant topic`.

**Good — self-contained clip**

- Rank 1 clip needs no VO: `needs_interviewer_tag: false`, high `clarity`.

**Bad — overlaps**

- Two highlights with overlapping `[start_ms, end_ms]` on the same source — invalid.

**Bad — five clips same 20s window**

- Violates “do not pick five clips from the same 30s window”.

**Bad — thin rejects**

- `rejected_candidates: []` or fewer than 3 entries when many segments existed — fails prompt contract.
