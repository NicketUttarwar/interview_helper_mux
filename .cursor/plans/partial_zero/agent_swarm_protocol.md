# Agent swarm protocol — Partial Zero

## Law

- **No product patches** without a logged operator verdict in `decision_log.md`.
- **Code is SSOT** (§0.3a). Docs/clinic/plans = hints only; verify or drop.
- **Partial without forensics** is the only success frame.
- **Tests follow HEAD** — update fixtures; do not preserve stale forensics-era expectations.

## Roles

| Role | May write | Must not |
|------|-----------|----------|
| Phase analyst | `analysis/*.md`, draft issue list | product code; final sole option |
| Caller census | junction caller tables | product code |
| Hint digester | `mohan_hint_digest.md` only from named exec_* | treat hints as proof |
| Solution-swarm member | `solution_swarm/DP-*/` | decide for operator |
| Devil’s advocate | attack leading option in swarm folder | suppress CUT options |
| Packet merge captain | `packets/DP-*.md` with ≥3 options + trade-offs | one-option packets; jargon-only TL;DR |
| Implementer | code + HEAD tests **after verdict** | undecided items |
| Companion | live Partial packets | patch without verdict |
| Phase merge captain | scorecard / matrix merges | drop minority findings silently |

## Solution-swarm (Phase B)

For each Decision Packet, spawn in parallel as needed:

1. patch-minimal  
2. family-root / SSOT  
3. SIMPLIFY  
4. CUT / retire  
5. Partial-operator-gate  
6. defer / learn-more  
7. devil’s advocate  
8. test/matrix designer  

Merge captain → ≥3 real options + Defer, trade-off card on **every** option, plain-language TL;DR, YOUR NEXT ACTIONS + PROGRESS_NOW / DIG_DEEPER.

## Parallelism

No agent-count budget. Critical Five phases may run concurrently. Each DP gets its own solution-swarm.

## Local ML fault order (§0.3b)

When recommending host behavior for local MusicGen / Chatterbox / STT / MMAudio / DeepFilter / local LLM: **kill related jobs → sleep 5s → retry → then escalate**. Time is never the priority.
