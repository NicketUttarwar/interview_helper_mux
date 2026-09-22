# Solution option draft — DP-A2 / family-root SSOT

- role: family-root | ssot
- one-line idea: One End-A allowlist owns ship-blocking omit/integrity; delete parallel `_ship_blocking_omit_ids` constitution and packaging substring auto-allow.
- what we would do:
  1. Add named actions to `HARD_FREEZE_ALLOWLIST_ACTIONS` for junction incomplete-cut omit kinds + `edl_overlap_repair` / `segment_id_remap`.
  2. Make `commit_selection_mutation` call `hard_freeze_action_permitted` (or map omit → named action) instead of a second list.
  3. Remove packaging substring bypass in `seat_mutation_allowed`; CTA gets named rows or meta-gate.
  4. Keep i30/i37 green via named rows.
- pros: Single audited constitution; Partial can land ship-repairs under freeze without operator unlock; packaging honesty.
- cons: Allowlist becomes the product surface; every new repair needs a row.
- trade-offs (Partial / cousins / complexity / give-up / human / cost / regression / reversibility):
  - Partial: high certainty
  - Cousins: closes FREEZE dual-list; packaging CUT
  - Complexity: medium stewardship
  - Give up: substring convenience
  - Human: verdict per named row
  - Cost: medium (seat_authority + air_order_boundary + tests)
  - Regression: medium (must preserve i30/i37)
  - Reversibility: high if rows flagged
- cousin closure claim: FREEZE_CONSTITUTION root; feeds A3 writer gates
- tests: End-A constitution requires ship-repair kinds on allowlist; packaging substring refuses; i29 omit under freeze still lands
