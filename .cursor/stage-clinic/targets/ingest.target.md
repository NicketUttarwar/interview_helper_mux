# Target Spec — ingest

brain: 0.2.0 | target_status: draft  
Wave 2 may implement `unambiguous` rows without further operator input.

## Ideal behavior (include Full-auto + defaults column)

| Permutation (from L1) | Required outcome (0.2.0) | Full-auto + defaults |
|----------------------|---------------------------|----------------------|
| `preclean/isolated.wav` present | ffmpeg from isolated → `normalized.wav` + loudness + checksums + done | Completes unattended after preclean |
| isolated missing, raw input present | ffmpeg from `input_audio()` → same artifacts + done | Completes (raw path) |
| no input audio | `FileNotFoundError` / refuse — no hollow done | Honest halt |
| ffmpeg failure | hard fail — no mark_done without primary wav | Honest halt |
| source_profile / readiness refresh throws | warn fail-open **after** mark_done; primary remains seated | Continues seed walk |
| loudness stabilize disabled / format-only | still write lineage + checksums + done | Completes |
| mid-write crash (normalized absent) | incompleteness / heal pin — not done-without-primary | Host rerun |

## Rules set (prefer deterministic)

- admit / when source file exists (isolated preferred, else raw)
- refuse / missing input audio; refuse / ffmpeg non-zero (no soft-lie done)
- wait_for_gate / never (no gate adjacency)
- incomplete / never mark_done without `ingest/normalized.wav` on disk
- precise invalidate / none from this stage (upstream preclean accept clears via clear_from)
- auto_resolve_default / N/A — no operator decision on this stage

## Complexity subtraction list

- Contract `remediation.strategies: volley_retry` — process stage has no LLM; host `full_stage_rerun` only
- Contract lifecycle phases listing `llm_execute` for a ffmpeg-only stage (claim noise)
- Ownership row `ingest/waveform_peaks.json` producer=`ingest` while body never writes peaks (GUI/lazy helper) — dual attribution risk

## Contract / dependency deltas (proposed; not applied)

- Drop `volley_retry` from `ingest.yaml` remediation; keep `full_stage_rerun` (or host-ffmpeg synonym via dependency data)
- Soft input stays optional `preclean/isolated.wav` — matches `_ingest_source`
- Re-home or annotate `waveform_peaks.json` ownership producer away from stage body if GUI is the only writer

## Non-goals

- ffmpeg / loudnorm / dynaudnorm tuning quality
- Changing preferred-source order (isolated then raw)
- Adding operator gates or Full-auto stalls on ingest
- Local heavy ML (none)

## Acceptance checks

- Missing input → no `.stage_done/ingest` and no hollow normalized claim
- Isolated present → checksums include `preclean_sha256`; ffmpeg input is isolated
- Isolated absent → ingest from raw; still hashes `input_audio()` as source lineage
- `STAGE_ARTIFACT_DISK_PATHS["ingest"]` / prepare_outputs require `ingest/normalized.wav`
- Contract remediation claim matches host rerun (no volley language after ING-B1)

## Upgrade backlog

| id | priority | unambiguous\|needs_you | summary | acceptance_hint | DoD check | FULL_AUTO_REGRESSION_RISK |
|----|----------|------------------------|---------|-----------------|-----------|---------------------------|
| ING-B1 | P1 | unambiguous | Align contract remediation: remove `volley_retry`; host ffmpeg rerun only | `ingest.yaml` via `contract_dependency_data` + verify script | 2 | no |
| ING-B2 | P2 | unambiguous | Drop or retarget process-stage `llm_execute` lifecycle claim noise on ingest contract | contract generator / dependency data | 2 | no |
| ING-B3 | P2 | answered→applied | ingest-only `waveform_peaks.json`; GUI load never writes (1B) | `persist_normalized_peaks` + StageInfo/contract | 2,7 | no |

## Defaults inventory impact

- Rows touched in `defaults_inventory.md`: none (ingest has no gate/stall/default landmine; loudness_stabilize is quality cfg only)

## target_status

`draft` — Wave 2 applied ING-B1/B2; ING-B3 **1B** applied (ingest-only peaks)
