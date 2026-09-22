# Solution option draft — DP-A2 / patch-minimal

- role: patch-minimal
- one-line idea: Keep dual constitution; document ship-blocking omit as the only intentional second list; leave packaging/catastrophe as separate escapes (docs + assert tests only).
- what we would do:
  1. No behavior change to End-A vs `_ship_blocking_omit_ids`.
  2. Document dual lists in seat_authority / air_order_boundary comments and Partial Zero freeze junction.
  3. Optionally add a test that both paths exist and packaging substring still bypasses budget.
- pros: Zero product risk; i30/i37 stay green; cheapest.
- cons: Does not close FREEZE_CONSTITUTION; operators still cannot reason from one file; packaging hole remains.
- trade-offs (Partial / cousins / complexity / give-up / human / cost / regression / reversibility):
  - Partial: medium-low
  - Cousins: none at root
  - Complexity: two modules forever
  - Give up: constitutional honesty
  - Human: docs only
  - Cost: near zero
  - Regression: low short-term
  - Reversibility: N/A
- cousin closure claim: None — status quo with labels
- tests: Doc/assert dual paths; weak for campaign close
