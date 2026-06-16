# Interview spine build

**Stage id:** `interview_spine_build`  
**Ticket:** BUILD-083  
**Spec:** [interview-spine.md](../../cross-cutting/interview-spine.md)

## When it runs

After G0 transcript review clears and **`source_acoustic_profile`** completes. Pipeline order:

`… → disfluency_extract → source_acoustic_profile → interview_spine_build → speaker_roles → …`

Blocked in `G0_LOCKED_ANALYSIS_STAGES` until review queue is complete (same as SAP).

## Inputs

| Path | Required |
|------|----------|
| `transcript/full.json` | Yes — G0-corrected words |
| `understanding/source_acoustic_profile.json` | Yes |
| `ingest/normalized.wav` | Yes |
| `preclean/isolated.wav` | Optional — preferred analysis WAV when present |

## Outputs

| Path | Description |
|------|-------------|
| `understanding/interview_spine.json` | Windows, boundary events, retrieval metadata |
| `understanding/interview_spine/embeddings.npz` | Optional CLAP vectors |

## Operator actions

1. Run analysis through **Source acoustic profile** (or full analyze).
2. Confirm **Interview comprehension spine** stage completes in pipeline.
3. Open **Story Board** → spine summary, or pipeline gate **Recompute spine** after ingest/transcript edits.
4. Optional: query moments via API **POST** `/api/runs/{id}/interview-spine/query` with `{ "query": "…", "top_k": 5 }`.

## Recompute

**POST** `/api/runs/{id}/recompute-interview-spine` — full rebuild from current inputs (idempotent skip when unchanged).

## Disable

Set `interview_spine.enabled: false` in config — stage marks done without writing artifact.
