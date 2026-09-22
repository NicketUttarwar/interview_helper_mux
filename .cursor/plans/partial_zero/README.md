# Partial Zero Campaign

**North star:** Error-free **partially_accelerated** Mohan run without forensic intervention.

**Law (short):**

1. Operator decides every issue (Decision Packets + STEP-OFF).
2. **Code is SSOT** — docs/clinic/plans are hints only; verify or drop on HEAD.
3. Fault tolerance over speed for local ML: kill stale jobs → sleep 5s → retry → then escalate.
4. Cousin families close at the root; tests follow current HEAD.
5. Every STEP_OFF ends with copy-paste `PROGRESS_NOW` for Cursor Agent.

## Start here

1. Read [`STEP_OFF.md`](STEP_OFF.md) — live status + `progress_now_paste`.
2. Read [`decision_queue.md`](decision_queue.md) — open packets.
3. Paste `progress_now_paste` into a Cursor Agent chat to continue.

## Index

| File | Purpose |
|------|---------|
| [STEP_OFF.md](STEP_OFF.md) | Live resume + PROGRESS_NOW |
| [resume_commands.md](resume_commands.md) | Command library |
| [decision_log.md](decision_log.md) | Append-only verdicts |
| [decision_queue.md](decision_queue.md) | Awaiting operator |
| [agent_swarm_protocol.md](agent_swarm_protocol.md) | Parallel agent roles |
| [phase_scorecard.md](phase_scorecard.md) | 12 journey phases |
| [cousin_matrix.md](cousin_matrix.md) | Failure families |
| [handoff_ledger.md](handoff_ledger.md) | Producer→consumer edges |
| [junction_register.md](junction_register.md) | Multi-caller junctions |
| [mohan_hint_digest.md](mohan_hint_digest.md) | HINT-only exec histograms |
| [cut_economics_ledger.md](cut_economics_ledger.md) | KEEP/SIMPLIFY/CUT scores |
| [pre_partial_go_nogo.md](pre_partial_go_nogo.md) | Launch gate packet |
| [closeout.md](closeout.md) | Closeout packet |
| [packets/](packets/) | One DP per issue |
| [templates/](templates/) | Packet / analysis templates |
| [analysis/](analysis/) | Four-level phase writes |

Plan SSOT (do not edit during campaign): `~/.cursor/plans/partial_zero_protocol_dcd491c4.plan.md`
