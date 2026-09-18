# Decisions — ingest

Append-only. Do not rewrite history.

| timestamp | layer | question | operator answer | implication |
|-----------|-------|----------|-----------------|-------------|
| 2026-09-18 | L3 | ING-B3 waveform_peaks dual writer? | **1B** ingest-only write; GUI read-only | `persist_normalized_peaks` from ingest; `load_or_generate_peaks` never writes; StageInfo + contract output |
