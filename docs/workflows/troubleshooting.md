# Troubleshooting playbook

**Environment:** Wrong package or CLI version → [anchored-toolchain.md](../cross-cutting/anchored-toolchain.md); re-run `./tools/check_prerequisites.sh` (includes `pip-audit` on lock).

Symptom → likely cause → **artifact to inspect** → **fix / re-run**. For re-run flags see [idempotent-runs.md](./idempotent-runs.md) and [feedback-loops-and-reruns.md](./feedback-loops-and-reruns.md).

---

## GUI / operator shell

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| Checkpoint modal shows wrong stage | Stale sidebar selection (fixed in current GUI) | Action modal title vs sidebar | Dismiss and reopen **Action**; modal auto-focuses blocking stage on all tabs |
| Listen button does nothing | No global `.audio-player` in Stage view | Gate panel inline audio | Use **Listen** again (inline player); check Logs if play fails |
| Record pickup fails silently | Mic permission denied | Browser site settings | Allow microphone; toast should appear on deny |
| Clear session but Executions still highlights run | Expected — list is historical | `ASSETS/.gui/active_execution.json` | **Clear session** clears server active pointer; use **Resume server session** on empty Pipeline if needed |
| Resume / Run step does nothing | Half-loaded session or stale `jobRunning` | Browser console; `active_execution.json` | Use **Retry load** on Pipeline/Start; refresh page; restart `./scripts/run.sh` reconciles stale jobs |
| Wrong tab after refresh | UI chrome not persisted (fixed in current GUI) | `active_execution.json` `active_tab` | Should restore tab/sub-tab; **Clear session** if stuck |
| Stale `gui_job.json` after server restart | Disk still `running` but thread gone | `gui_job.json` → `interrupted` on serve | Re-run stage; **Run step** should enable after refresh |
| Job already running toast | Concurrent `POST …/execute` or in-process lock | `gui_job.json`; server lock | Wait for job poll; refresh after restart; open **Logs** |
| Stuck on **Reuse or run fresh** | `needs_stage_reuse` without decision | `gui_job.json`, action modal | Open **Action** → **Reuse outputs** or **Run fresh instead** |
| Stuck on **Review before save** | Staged outputs awaiting approve | `.pending_writes/<stage>/`, `gui_job.status: awaiting_write_approval` | Open action modal → preview files → **Save & continue** or **Discard & re-run** |
| Reuse offer missing | No prior run with same hash + completed stage | `run_meta.source_audio_hash`, prior `.stage_done/` | Complete stage on prior exec first; legacy runs may need same `input_audio_path` |
| Hash mismatch between runs | Different canonical WAV bytes | `source_audio_hash_short` in Executions list | Expected — only reuse when **Same audio** pill shows |
| QC fail with no guidance | Strict narrative/EDL QC | `run_meta.qc_summaries` | Read errors in gate panel; **View Logs**; **Redo from selected stage** |

---

## Pipeline / CLI

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| Stage skipped unexpectedly | `.stage_done/` marker present | `.stage_done/<stage>` | Delete marker for that stage **and** downstream only if you intend re-run; or use `--from-stage` |
| `run_analysis.py` stops mid-run | Gate G0 or `needs` in envelope | `transcript/review_queue.json`, `gui_log.jsonl`, `understanding/stage_runs/.../attempt_*.json` | Complete G0; fix `needs` per envelope |
| Wrong run directory | `--run-id` mismatch | `run_meta.json` | Pass correct `--run-id` / execution folder |

---

## LLM flow hardening gates

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| `LLM stage gate (…)` / job status `gate` | Critical stage envelope or artifact not acceptable | `understanding/stage_runs/<stage>/attempt_*.json`, producer JSON, `gui_log.jsonl` | Fix cited artifact; `--from-stage <stage>` |
| `Cross-artifact gate (…)` | Manifest/boundary/gap segment_ids inconsistent | `segments/manifest.json`, `segments/boundaries.json`, `gap_evaluations.json` | Re-run segmentation or gaps from failing stage |
| `Analysis artifacts gate` at flow start | Analysis incomplete under hardening | `analysis_state.json` `completion.blockers` | Complete analysis; **Fill gaps** on partial JSON |
| Preflight blocked (no OpenAI call) | Missing transcript, G0, or upstream artifact | `gui_log.jsonl` preflight line | Clear G0; ensure prerequisite stage artifacts exist |
| Investigation rerun stays open | Rerun did not improve artifact | `investigation_queue.json`, stage artifact status | Fix root cause; manual rerun or specialist |
| Investigation queue drain stuck | Orchestrator cap or repeated open items block progress | `understanding/investigation_queue.json`, `analysis_orchestration.json` | Drain open items via Story Board; fix cited artifact; `--from-stage` on producer; check `max_investigation_reruns_per_kind` |
| Same investigation re-runs every stage | Drain runs but artifact never reaches `complete` | `understanding/stage_runs/<stage>/attempt_*.json`, producer JSON status | Fix root artifact; `--from-stage <stage>` after manual edit |
| `rerun cap reached for kind=` in log | `max_investigation_reruns_per_kind` (default 2) exhausted | `analysis_orchestration.json` `investigation_rerun_counts` | Mark `wont_fix` in GUI if acceptable; or fix inputs and delete count key (dev) |
| Investigations duplicate same question | Dedupe off or different dedupe keys | Two open items' `kind`, `target.window_id` | Enable `investigation_dedupe`; resolve one manually |
| Queue enqueues but never drains | Non-LLM stage path / runner missing | `suggested_action.stage` vs `llm_stage_runners` keys | Ensure stage in `ALL_LLM_STAGES`; `--from-stage` to registered stage |
| Trust dip investigations on quiet speech | Missing corroboration gate | `spine.boundary_events`, `transcript/full.json` words near `time_ms` | Expected skip when no low-conf words; verify Wave A H-ING-03 not double-flagging |
| Too many `acoustic_anomaly` after content_context | >5 quality flags | `value_features.json` `quality_trajectory_flags` | Cap is 5; tune value analysis thresholds in Wave A |
| topic_drift + topic_drift duplicate | Stub not suppressed | `coherence.replace_stub_topic_shift_hints`, duration | Enable replace stub; verify ORC-03 gate on long runs only |
| Coherence risks on 20m interview | Duration miscount | `coherence_report.json` `gate.duration_ms` | Verify transcript word `end_ms`; should show `activated: false` |
| Blocking contradiction on emotional story beat | trauma_adjacent false positive | `coherence_report.json` risks near emotional peak, `content_brief.json` `key_claims` | Re-anchor brief; mark investigation `wont_fix` if narrative-intentional tension |
| topic_drift without audible change | Novelty fallback too sensitive | `scores[].novelty_score`, CLAP embeddings present? | Set `require_acoustic_novelty: true`; raise `novelty_min_delta` |
| No risks on 31m fixture | Gate or spine missing | `interview_spine/spine.json`, `orc03_enabled` | Run full analysis through `content_brief_reanchor`; run planted fixture test |
| `Open blocking claim_contradiction` | High-confidence contradiction unresolved | `investigation_queue.json`, `coherence_report.json` | Run `content_brief_reanchor`; resolve or `wont_fix` with operator note |
| Ready false but queue empty | Artifact incomplete under hardening | `analysis_state.json` `completion.blockers` | Complete partial producer JSON per blocker path |
| Shard collate blocked | `< shard_min_success_ratio` shards succeeded | `stage_runs/<stage>/` shard attempts | Fix shard inputs or lower ratio (dev only) |

Set `analysis.flow_hardening.enabled: false` only for intentional legacy/dev runs. See [LLM-ANALYSIS-ARCHITECTURE.md §18](../../LLM-ANALYSIS-ARCHITECTURE.md#18-flow-hardening).

**Investigation recovery commands:**

```bash
# Re-run from content brief after operator edits
python tools/run_analysis.py --run-id <id> --from-stage content_context

# Re-anchor only
python tools/run_analysis.py --run-id <id> --from-stage content_brief_reanchor

# Recompute coherence without full pipeline (GUI or API)
curl -X POST http://localhost:8765/api/runs/<id>/recompute-coherence \
  -H 'Content-Type: application/json' -d '{"phase":"post_reanchor"}'
```

See [analysis-orchestration-loop.md](./analysis-orchestration-loop.md) for orchestrator caps (`max_queue_drains_per_stage`, `max_investigation_reruns_per_kind`, `investigation_dedupe`).

---

## LLM loop stuck, arbiter lint fail, SDP cross-validate recovery

Symptoms from `attempt_budget.py` and `deterministic_lint.py` when quality-first routing blocks merge. Config: [config-keys.md](../cross-cutting/config-keys.md) (`max_primary_attempts_per_stage`, `stuck_signature_threshold`). Architecture: [LLM-ANALYSIS-ARCHITECTURE.md §20](../../LLM-ANALYSIS-ARCHITECTURE.md#20-loop-policy).

### LLM loop stuck (attempt budget exhausted)

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| `primary attempt budget exhausted (N/N)` | Same stage retried without fixing root cause | `understanding/analysis_orchestration.json` `primary_attempt_counts`, latest `attempt_*.json` `budget_remaining_primary` | Fix upstream artifact cited in `gaps` / lint; `--from-stage <stage>` after edit |
| `stuck_count` ≥ `stuck_signature_threshold` | Identical envelope signature across attempts | `attempt_*.json` `attempt_signature`, `stuck_count` | Change inputs (transcript, manifest, profile) — not just re-execute |
| `arbiter reject budget exhausted` | Repeated `retry_uptier` / `decompose` without improvement | `arbiter_reject_counts`, `arbiter_verdict` per attempt | Fill gaps on producer JSON; verify profile `operator_verified` |
| Stage done but artifact still `partial` | Merge blocked by lint or arbiter | `deterministic_lint_errors`, `should_merge_envelope` outcome | Complete artifact in GUI; re-run stage |

**Do not** raise `max_primary_attempts_per_stage` in production to “force through” — inspect `stage_runs/<stage>/attempt_*.json` and [stage-quality-scorecard.md](../cross-cutting/stage-quality-scorecard.md) for the stage tier.

### Arbiter lint fail (deterministic pre-check)

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| `deterministic_lint_errors` in attempt audit | Machine check failed before arbiter merge | Rubric `deterministic_lint_keys` in `arbiter-rubrics/<stage>.json` | Fix specific key (e.g. `schema_errors_empty`, `producer_artifact_complete`) |
| Arbiter `accept` but merge blocked | `confidence_gte_min` or `halt_on_schema_errors_with_accept` | Envelope `confidence` vs `min_confidence_on_accept` | Re-run with stronger tier or fix truncation via decompose |
| `cross_artifact_refs_valid` | Stage output references unknown `segment_id` | Envelope artifacts vs `segments/manifest.json` | Fix orphan ids in producer JSON; re-run upstream segmentation if manifest stale |
| `segment_coverage_ratio` below threshold | Decompose-eligible stage cites too few manifest segments | Rubric `min_segment_coverage_ratio` (default 0.85) | Add missing segment refs or lower ratio per rubric for intentional partial coverage |
| `min_row_count_met` | Empty speakers/boundaries when transcript warrants rows | `speakers.json`, `boundaries.json`, transcript duration | Re-run `speaker_roles` / `boundary_detection` with full volley |
| `truncation_requires_decompose` | Volley capped; stage is decompose-eligible | `truncation_flags` in attempt | Allow `decompose` path or reduce input size upstream |
| Low-confidence accept downgraded | `confidence < min_confidence_on_accept` | `stage_expectations` in arbiter payload | Tighten volley evidence or fix partial coverage |
| `Mix gate:` on `mix_flow*` | `block_mix_without_sfx_when_enabled: true` and WAVs missing | `sound_design/assets/`, `pre_mix_*` cross-validate errors | Re-run `mmaudio_sfx_flow*`; set `block_mix_without_sfx_when_enabled: false` only for dry-mix dev |

Lint reference: [arbiter-stage-rubrics.md](../prompts/_shared/arbiter-stage-rubrics.md) deterministic lint keys table.

### Cross-validate SDP recovery

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| `Cross-artifact gate (post_sound_palettes)` | Palette `segment_id` ∉ manifest or missing `sonic_identity` | `understanding/sound_design_plan.json` `palettes`, `coherence` | Re-run `sound_design_palettes`; fix manifest first if ids wrong |
| `post_sound_plan_flow1` / `flow2` fail | Cue anchors reference missing selection ranks or assets over cap | SDP `cues[]`, `flow_1_master/selection.json` or Flow 2 `selection.json` | Re-run `sound_design_plan_flow*` after fixing ranking/highlights |
| `pre_sfx_generation` blocked | Craft prompts missing or `asset_id` mismatch | `sfx_prompts.json`, SDP `assets[]` | Re-run `sfx_prompt_craft`; verify G1.5 approval if enabled |
| `pre_mix_flow1` / `pre_mix_flow2` fail | Generated WAV missing for planned `asset_id` | `sound_design/assets/`, `.stage_done/mmaudio_sfx_*` | Re-run generate stage; check `spend_block_stages` prerequisites |
| Placement QA hints ignored | Beds too hot or wrong duck | `sound_design/placement_adjustments.json`, `gui_log.jsonl` | Adjust SDP cue levels; confirm `sound_design.placement_qa_enabled: true`; re-run `mmaudio_sfx_flow*` or mix after editing adjustments |

Module: `sdp_cross_validate.py`. Spend gates: `llm_flow_hardening.require_spend_prerequisites()`. Recovery playbook: fix cited producer → delete downstream `.stage_done` only if needed → `--from-stage` at failing producer.

---

## LLM artifacts and validation

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| Stage output **pending** | Stage not run or persist blocked | `.stage_done/<stage>`, `gui_log.jsonl`, `understanding/stage_runs/<stage>/attempt_*.json` | Run stage; fix arbiter reject or schema errors in attempt audit |
| **partial** after stage marked done | Semantic gaps or invalid JSON on disk | File content vs [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md) | **Fill gaps** in GUI or `--from-stage <producer>` |
| GUI save fails / schema toast | Zod or server jsonschema | Editor status lines, response `errors[]` | Fix fields; compare to `docs/cross-cutting/json-schemas/` |
| `content_brief.json` missing themes in profile | `memory_updates` not merged | Latest `content_context` attempt envelope | Re-run `content_context`; check arbiter `accept` |
| Operator themes overwritten | Profile not verified | `analysis_state.json` `meta.operator_verified` | Mark verified; re-run from stage |
| Profile gate (BUILD-081) blocks Flow 1 | `selected_flow: flow1` and `meta.operator_verified` not true before `topic_coverage_audit` | `analysis_state.json`, `run_meta.json`, `gui_log.jsonl` `stage=analysis_profile` | Open Story/Profile; **Mark profile verified**; `--from-stage topic_coverage_audit` |
| Coherence blocking contradiction | High-confidence `claim_contradiction` risk with `coherence.blocking_claim_contradiction: true` | `understanding/coherence_report.json` `risks[]`, `analysis_state.json` `completion.blockers` | Resolve contradiction in transcript/brief; re-run `topic_coverage_audit` or upstream analysis |
| Pipeline re-runs same stage unexpectedly | Incomplete artifact guard | `artifact_completeness.should_run_stage_for_artifact` | Complete file or edit to valid shape |

---

## Transcript review (G0) and dock

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| Fuzzy panel shows no matches | Strictness too high or correction not typed yet | Panel hint text; slider at 80% | Type a different correction; lower strictness toward 80% |
| Batch replace did not apply | **Also replace similar matches** unchecked | Popover checkbox; button label “Replace this word” | Check box and click **Replace N words** |
| Edit closes when clicking panel | Blur before fix (older builds) | — | Current GUI defers blur when focus stays in `.fuzzy-replace-popover` |
| Dock save failed | Network or invalid index | Browser network tab, `gui_log.jsonl` | Retry edit; reload transcript (`GET …/transcript`) |
| Chunk save OK but `full.json` unchanged | Expected until G0 complete | `transcript/corrections.json` vs `full.json` | **Complete transcript review** to merge chunk text |
| Chunk textarea stale after dock edit | Fixed in current GUI — reload on save | `corrected_text` in `review_queue.json` | Dock save syncs queue; textarea auto-refreshes |
| Batch replace mistake | Undo available | Dock toolbar **Undo** or ⌘Z | Reverts last edit batch via `PATCH …/transcript/words` |
| Review order unexpected | Salience sort (not confidence-only) | `transcript/review_queue.json` `sort_mode`, `chunks[].rank` | Default `salience`; set `transcript_review.sort_mode: confidence` for legacy order; re-run `--from-stage transcript_review_build` |
| Top clips lack audible issues | Pause proxy inflated rank on reflective speech | `chunks[].acoustic_stress_score`, salience weights | Listen to top ranks; stress term (0.2) should corroborate — see [transcript-quality-rubric.md](../prompts/_shared/transcript-quality-rubric.md) |

---

## Disfluency review (G0.5)

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| G0.5 stuck / analysis blocked before SAP | Filler events pending review | `transcript/disfluencies.json`, `.stage_done/disfluency_review` | Open **Disfluency review**; confirm/reject events; **Complete review** — [operator-gates.md](./operator-gates.md#g05--disfluency-review-filler-clips) |
| G0.5 auto-skipped | `disfluency_extract.enabled: false` or zero events | `config/app.defaults.json`, `disfluencies.json` | Expected fail-open; enable extract if filler review needed |
| `disfluency_review` pending in GUI | Checkpoint banner on disfluency stage | `gui_log.jsonl` `stage=disfluency_review` | Complete review or disable extract for unattended runs |

---

## Transcription (AWS)

### Symptom table (behavioral)

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| No `full.json` | Job failed or not polled | CLI / cloud logs, S3 keys | Re-`transcribe`; verify `AWS_S3_BUCKET`, region, credentials |
| Broken timestamps | Bad audio or Transcribe glitch | `transcript/full.json` words | `--from-stage transcribe` after fixing source |
| Missing speakers | Diarization off | `transcript/speakers.json` | Re-transcribe; check channel layout / mono merge |
| Job stuck “IN_PROGRESS” forever | Rare service stall or bad object | `aws transcribe get-transcription-job`, S3 object size | Cancel job; re-upload; open AWS support if regional outage |

### AWS CLI and S3 (`aws s3 cp`) — strings in the wild

Match **substrings** in stderr / exit output (wording varies by CLI version). Treat as heuristics, not exhaustive.

| If you see (substring) | Meaning | Inspect | Action |
|------------------------|---------|---------|--------|
| `AccessDenied` / `Access Denied` / `403` | IAM or bucket policy blocks principal or object ACL | Caller identity, bucket policy, object ownership | Fix IAM role/user policy; ensure bucket allows `s3:PutObject` / `GetObject` for your ARN |
| `InvalidAccessKeyId` / `SignatureDoesNotMatch` | Wrong or rotated static key | `secrets.env`, env vars | Rotate keys; fix `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` |
| `ExpiredToken` / `RequestExpired` / `security token included in the request is expired` | STS session ended | SSO / assumed-role session | Re-login (`aws sso login`, refresh role chain) |
| `NoSuchBucket` / `Not Found` + bucket name | Wrong `AWS_S3_BUCKET` or typo | `config/secrets/secrets.env` | Fix bucket string; create bucket if intentional |
| `404` + `NoSuchKey` / `NotFound` + key | Wrong `AWS_S3_INPUT_KEY` or object deleted | Key in config vs `aws s3 ls` | Fix key prefix; re-upload `normalized.wav` |
| `PermanentRedirect` / `endpoint` mismatch | Wrong region endpoint for bucket | Bucket region vs `AWS_DEFAULT_REGION` | Use `aws s3api get-bucket-location`; align region |
| `IllegalLocationConstraintException` | Create-bucket in wrong region | CLI args | Create bucket in same region as Transcribe job |
| `SlowDown` / `503` / `Please reduce your request rate` | S3 throttling | Large parallel uploads | Backoff; serial uploads; smaller multipart |
| `Could not connect` / `Connection reset` / `TLS` / `timeout` | Network / proxy / VPN | Local network, corporate proxy | Retry; fix proxy; verify TLS intercept |
| `KMS` + `AccessDeniedException` | SSE-KMS key policy | Bucket default encryption | Grant KMS decrypt/encrypt to uploading principal |
| `EntityTooSmall` / `IncompleteBody` | Truncated upload | File size vs source | Re-`cp`; verify disk read no errors |
| `fatal error: An error occurred (InvalidRequest)` when uploading | Sometimes encryption headers / ACL mismatch | Bucket policy | Compare with working bucket; remove legacy ACL expectations |

### Amazon Transcribe — job API and console

| If you see | Meaning | Inspect | Action |
|------------|---------|---------|--------|
| `get-transcription-job` → `FAILED` | Transcribe rejected job | `FailureReason` field in JSON | Fix media (codec, sample rate, size); fix S3 URI; see reason text |
| `Unsupported media format` / `format` in FailureReason | WAV/container not supported | `ffprobe` on `normalized.wav` | Re-ingest to supported PCM WAV per ingest spec |
| `The URI that you provided doesn't refer to an S3 object` | Bad `MediaFileUri` | Job request params / app config | Fix bucket + key template |
| `Access denied` inside FailureReason | Transcribe service role cannot read object | Bucket policy, KMS, object ACL | Add `transcribe.amazonaws.com` principal or correct object grant |
| Job completes but JSON empty / odd | Rare parse or zero audio | Source file | Listen to normalized; check duration |

**Guard:** Always capture **`FailureReason`** from `get-transcription-job` when reporting bugs — it is the authoritative Transcribe error string.

---

## LLM / JSON validation

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| Log: “Schema validation failed” | `artifacts` ≠ stage schema | Same stage `attempt_*.json` + error list | Model retry may fix; else tighten prompt input (profile, manifest size) |
| `segment_classification` fails | Invalid `type` / `speaker_role` / `flags` | Error path in message | Use only enums from [segment-schema.md](../cross-cutting/segment-schema.md) |
| Repeated `theme_unmapped` | Brief topic has no segments | `coverage_audit.json`, `manifest.json` | Re-classify or add `topic_tags` to segments |

**Guard:** New stages must register in `STAGE_ARTIFACT_SCHEMAS` — see [json-schema-coverage.md](../cross-cutting/json-schema-coverage.md).

---

## Segmentation & gaps

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| Absurd segment count | Over-splitting | `segments/boundaries.json` | `--from-stage boundary_detection` with clearer brief |
| Wrong gap types | STT errors in segment text | `segments/manifest.json` text | Fix G0 transcript first, then `--from-stage missing_framing` |
| `value_analysis_skip_no_wav` in log | Auto-extract enabled but `ingest/normalized.wav` missing | `gui_log.jsonl` `stage=content_context` or `value_analysis_extract` | Expected fail-open — transcript profile still extracts; run ingest before audio profile or disable `value_analysis.audio_features` |
| Trust-dip flags in `value_features.json` | RMS proxy flagged listener-trust windows (H-ING-03) | `understanding/value_features.json` `profiles.transcript.quality_trajectory_flags` | Review flagged windows in GUI log (`value_features: N trust-dip flags`); re-run `--from-stage value_analysis_extract` or `python tools/extract_value_features.py --run-id <id> --profile transcript` |
| `Pre-stage specialist comprehension_risk_blind failed` | Specialist timeout/API error (fail-open) | `understanding/stage_runs/missing_framing/specialist_comprehension_risk_blind.json` | `missing_framing` continues without risks; fix API/network; re-run `--from-stage missing_framing`; optional investigation enqueued when flow hardening on |
| G1 never clears | Missing WAV or wrong filename | `gap_report.json`, `vo_pickup/` | Match `{line_id}.wav` or `{targets_segment_id}.wav` — [operator-gates.md](./operator-gates.md) |

---

## Flow 1 ordering & narrative

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| Duplicate `segment_id` in order | Model error | `flow_1_master/selection.json` | `--from-stage full_master_ranking`; fix manifest if ids wrong |
| Constraint violation | `narrative_plan.ordering_constraints` impossible | `narrative_plan.json` + `selection.json` | Edit plan or re-run `narrative_arc_plan` |
| Topic missing in master | Excluded without rationale | `selection.excluded_segment_ids`, `coverage_audit` | Re-audit or adjust exclusions |
| `validate_narrative.py` fails | Brief topic unmapped or empty chapter | `coverage_audit.json`, `selection.json` | Fix audit/ranking; or set `narrative_qc.strict: false` to warn-only |
| `validate_narrative.py --include-edl` fails | Final EDL breaks coverage, chapter continuity, ordering constraints, transition anchors, or gap placements | `edl_narrative_audit.json`, `selection.json`, `narrative_plan.json`, `transitions.json`, `edl.json` | Fix recommended artifact; usually re-run `full_master_ranking`, `transitions`, `vo_ingest`, or `edl_flow1` |
| `validate_edl.py` fails | Invalid EDL timeline events or bounds | `flow_1_master/edl.json` event paths | Re-run `edl_flow1` after fixing selection/transitions/VO paths |
| `verify_edl.py` fails | EDL JSON schema shape invalid | `flow_1_master/edl.json` schema paths | Fix EDL writer or malformed manual edit; re-run `edl_flow1` |

---

## Flow 2 highlights

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| Overlapping clips | Selection error | `flow_2_highlights/selection.json` | `--from-stage highlight_selection` |
| All clips same topic | Diversity not enforced | `scores.diversity_bonus`, `rejected_candidates` | Re-run selection; tighten brief audience |

---

## Flow 3 show description

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| Blurb uses "we" / "you" | First/second person leak | `flow_3_description/show_description.json` → `description_markdown` | Re-run `podcast_show_description`; see [examples](../prompts/_shared/examples/podcast-show-description.examples.md) |
| Too short or too long | Word count out of band | `word_count` field | Re-run stage; adjust `show_description_*_words` in [config-keys.md](../cross-cutting/config-keys.md) |
| Generic hype, no specifics | Thin volley or weak brief | `content_brief.json`, `analysis_state.json`, `stage_runs/podcast_show_description/` | Verify profile; `--from-stage content_context` |
| `show_description_qc` strict halt | Word count, person, or hype violations with `show_description_qc.strict: true` | `flow_3_description/show_description.json`, `run_meta.qc_summaries` | Fix copy in GUI or re-run `podcast_show_description`; `python tools/validate_show_description.py --run-id <id>` |
| Invented facts | Model drift | `evidence_segment_ids`, transcript | Re-run with verified profile; tighten prompt guardrails |

---

## Audio / mix

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| No VO in `master.wav` | Missing `vo_pickup/` files, EDL gap placements, or mix skipped | `flow_1_master/edl.json`, `vo_pickup/`, `.stage_done/mix_flow1` | Match WAV filenames to `gap_report`; `--from-stage edl_flow1` then `assembly_preview`; re-run `mix_flow1` — [assembly_and_mux](../pipeline/assembly_and_mux/README.md) |
| SFX unused in master | Missing SDP assets, craft/generate not run, or empty cues | `understanding/sound_design_plan.json`, `sound_design/assets/`, `.stage_done/mmaudio_sfx_flow1` | Re-run `sound_design_plan_flow1` → craft → generate → `mix_flow1`; verify cue `asset_id` links — [sound-design.md](../cross-cutting/sound-design.md) |
| SFX feels random | Weak palette/plan or skipped post-listen QA | SDP `coherence`, `sfx_prompts.json` | Re-run `sound_design_palettes` / flow plan; enable G1.5 (`g1_5_require_prompt_approval: true`) |
| Loudness wrong | Master out of LUFS/peak spec | `verify_master.py` failure lines; re-run `master_flow*` after fix | [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md) |
| GUI auto-runs `verify_master` after `master_flow*` | Post-master QC in `web/runner.py` | `run_meta.qc_summaries`, `gui_log.jsonl` `stage=verify_master` | Fix mix levels; re-run `master_flow*`; read LUFS/peak lines in gate panel |
| Spine recompute invalidates Story Board | SAP or spine rebuild clears downstream markers | `gui_log.jsonl` invalidation lines, `.stage_done/` | Re-run from invalidated stage; confirm `execution_invalidation.py` scope — [gui-surface-map.md](./gui-surface-map.md) Story Board |
| Recompute spine failed | Missing transcript, SAP, or WAV after G0 | `gui_log.jsonl` `interview_spine_recompute_failed`; HTTP 500 from `POST …/recompute-interview-spine` | Complete G0 + `source_acoustic_profile`; verify `ingest/normalized.wav` or preclean isolated path |
| boundary_detection volley truncated | Many spine boundary events; volley cap 40 | `gui_log.jsonl` `boundary_detection volley truncated` | Review full `understanding/interview_spine.json`; check for over-segmentation upstream |

---

## MMAudio SFX + DeepFilterNet preclean

**Canonical guide:** [local-audio-stack.md](../cross-cutting/local-audio-stack.md). **Checklists:** [operator-stage-checklists.md § MMAudio SFX](./operator-stage-checklists.md#mmaudio-sfx--preclean).

### HTTP / API

| If you see | Meaning | Inspect | Action |
|------------|---------|---------|--------|
| `401` / `Unauthorized` | Bad or missing API key | `` | Fix secrets; reload env; **do not retry** |
| `429` / `rate limit` / `too many requests` | Quota or burst cap | Logs, dashboard | Backoff 2^n s (n=1..5); ≤2 parallel; serialize assets |
| `402` / payment (varies by vendor copy) | Billing / plan | removed cloud audio billing (use local MMAudio) | Stop generation; resolve billing |
| `5xx` / timeout | Server or network | Payload size, proxy | Retry 5s, 15s, 45s (max 3); then placeholder WAV (target) |
| Timeout / empty body | Network or large file | Isolation file duration | Retry once; for isolation use streaming/chunking when implemented |

### Quality / product

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| SFX unused in master | Missing assets or mix not run | SDP `assets[]`, `sound_design/assets/`, `.stage_done/mix_flow*` | Re-run craft → generate → `mix_flow1` / `mix_flow2`; check cue `asset_id` references — [stage-registry](../build-out/stage-registry.md) |
| Random / trailer feel | Weak craft or legacy v1 brief path | SDP + `sfx_prompts.json` | Default: SDP + craft; tune [prompt_influence](../cross-cutting/local-audio-stack.md) |
| Wrong timbre after regen | Variance or influence | `sfx_prompts.json` | [Regression appendix](../prompts/_shared/examples/sfx-prompt-regression.md); rewrite prompt |
| Voice in generated bed | Weak craft | `sfx_prompts.json` | Regen; strengthen `negative_prompt`; block policy strings |
| Bed buries speech | Level / duck too hot | SDP cues `level_db`, `duck_under_speech_db` | Post-gen: lower bed −4 dB or duck +4 dB — [sound-design.md](../cross-cutting/sound-design.md) |
| Harsh montage cuts | Fixed concat / no crossfade | Flow 2 selection ranks | Post-gen: 80–200 ms crossfade; lower transition level |
| Isolation underwater | Over-processing | A/B raw vs `preclean/isolated.wav` | Disable pre-clean; try `rnnoise_local` |
| Cost spike | Per-cue v1 or regen loop | # API calls vs unique `asset_id`s | Enforce reuse; idempotent skip; G1.5 approval |
| Regen loop | Plan hash not updating | SDP + `sfx_prompts.json` | Fix craft; cap 2 regens per asset |
| MMAudio semantic QA skipped (`missing_wav`) | CLAP/MMAudio venv unavailable or asset WAV missing | `sound_design/assets/*.json` `semantic_qa_verdict=skipped`, `skipped_reason` | Fail-open — review craft manually; bootstrap MMAudio venv per [local-audio-stack.md](../cross-cutting/local-audio-stack.md) |

### Spend controls

- Run **assembly_preview** before SFX spend.
- Enable **G1.5** (`g1_5_require_prompt_approval: true`) for high-cost runs.
- Target architecture: one call per `asset_id`, not per cue.

---

## NLE / timeline

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| Timeline edits ignored | Stale selection/EDL | `segments/nle_edits.json` vs `selection.json` | **Save timeline**, then re-run from `full_master_ranking` or `edl_flow1` — [feedback-loops-and-reruns.md](./feedback-loops-and-reruns.md) |

---

## Still stuck?

1. Read the latest `understanding/stage_runs/<stage>/attempt_*.json` for `context_volley` and validation errors.
2. Confirm [operator-stage-checklists.md](./operator-stage-checklists.md) for the stage you just ran.
3. Open [json-schema-coverage.md](../cross-cutting/json-schema-coverage.md) to see whether the artifact you edited is schema-backed.

---

## Related

- [smoke-test.md](./smoke-test.md) — greenfield machine checklist
- [analysis-orchestration-loop.md](./analysis-orchestration-loop.md) — envelope `status` / `needs`
- [pipeline/transcription/README.md](../pipeline/transcription/README.md) — AWS stage overview
- [pipeline/transcription/stt-and-diarization.md](../pipeline/transcription/stt-and-diarization.md) — STT/diarization catalog
- [pipeline/transcription/source-separation-and-enhancement.md](../pipeline/transcription/source-separation-and-enhancement.md) — denoise / separation
- [workflows/gui-surface-map.md](./gui-surface-map.md) — GUI ↔ logs ↔ artifacts
- [prompts/sound_design/guardrails-and-edge-cases.md](../prompts/sound_design/guardrails-and-edge-cases.md) — SDP / mix rails (Wave 5)
