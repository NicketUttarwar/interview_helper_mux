# Resume / progress commands — Partial Zero

Paste into **Cursor Agent** chat (unless noted).

## Primary

### `/partial-zero-progress` (PROGRESS_NOW)
```
/partial-zero-progress
Read .cursor/plans/partial_zero/STEP_OFF.md and decision_queue.md.
Next unit: <from STEP_OFF>.
Goal: error-free partially_accelerated without forensics.
Code is SSOT; docs are hints only.
Do only the next unlocked step; end with an updated PROGRESS_NOW for whatever follows.
Do not decide for the operator. Do not start forensics.
```

### `/partial-zero-resume`
Same as reading STEP_OFF + pasting `progress_now_paste`.

## Decisions

### `/partial-zero-answer`
```
/partial-zero-answer DP=<id> VERDICT=<A|B|C|Defer|custom> NOTES=...
Log verdict to decision_log.md; unlock implement for that DP only; emit IMPLEMENT_NEXT + refresh PROGRESS_NOW.
```

### `/partial-zero-implement`
```
/partial-zero-implement DP=<id> VERDICT=<…>
Implement only the logged verdict. Update cousin-matrix tests for current HEAD (MUX_FORENSICS=0).
Refresh STEP_OFF + next PROGRESS_NOW. Do not start forensics.
```

### `/partial-zero-more-options` / `/partial-zero-explain-simple`
Re-open swarm or simplify language; **no implement**.

### `/partial-zero-batch-summary` / `/partial-zero-batch-continue` / `/partial-zero-pause`
Batch UX; continue unlocks only decided items; pause refreshes STEP_OFF.

## Analysis / launch

### `/partial-zero-swarm PHASE=<id>`
Spawn unlimited analysts for one phase; draft DPs; no patches.

### `/partial-zero-pre-partial`
Draft go/no-go packet.

### `/partial-companion RUN=<exec_id>`
Watch Partial only; code intervenes only via new DPs + operator verdict.

### `/partial-zero-closeout`
Draft closeout packet; freeze forensics only after operator verdict.
