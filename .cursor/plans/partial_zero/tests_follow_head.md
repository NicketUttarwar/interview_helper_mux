# Tests follow HEAD — Partial Zero

**Rule:** Cascade / cousin-matrix / junction tests must lock **current HEAD** Partial-safe behavior the operator approved.

- Prefer parameterized matrix tests over single-predicate forensics souvenirs.
- When HEAD changes under an approved DP, **update or retire** fixtures that encode obsolete predicates, stale ownership, or forensics-only thrash.
- Run under `MUX_FORENSICS=0` for cascade honesty.
- Do not keep failing tests “to remember” old campaigns — move history to plan notes; tests must green on HEAD.

Implementers: after each logged verdict, add/update tests named by family/junction (e.g. `test_junction_precede_matrix_*`), not only `test_iNN_*` surface IDs.
