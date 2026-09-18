# Decisions — transcribe

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-17 | L3 | TR-B4 empty words → incomplete vs done? | **4B KEEP empty-words done** (confirm) | `transcribe_local` marks done after write even when `words=[]`; thin tape keep progressing; G0 owns repair |
