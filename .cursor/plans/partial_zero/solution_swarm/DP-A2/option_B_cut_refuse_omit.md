# Solution option draft — DP-A2 / cut

- role: cut
- one-line idea: Permanent freeze = End-A only; **refuse** ship-blocking omits until operator unlock (mix/PMQ stay red).
- what we would do:
  1. Delete or ignore `_ship_blocking_omit_ids` proceed path under hard freeze.
  2. Freeze restores omitted ids or refuse commit — incomplete_cut remains until unlock.
  3. Update i30/i37 to expect refuse/red (or retire those paths under freeze).
- pros: Narrowest paper allowlist; no hidden second module; matches mechanism honesty Decision A2-2.
- cons: Reopens exec_11871 deadlock class; Partial cannot clear incomplete_cut unattended — fails Partial-without-forensics.
- trade-offs (Partial / cousins / complexity / give-up / human / cost / regression / reversibility):
  - Partial: low (deadlock)
  - Cousins: dual-list closed by amputation; MIX incomplete_cut reopens
  - Complexity: low code / high ops
  - Give up: unattended junction heal under freeze
  - Human: unlock every stuck omit
  - Cost: low–medium
  - Regression: high (known deadlock)
  - Reversibility: medium
- cousin closure claim: Dual constitution gone; ship-block cousin reopened as operator work
- tests: omit refused under freeze; mix remains incomplete_cut until unlock
