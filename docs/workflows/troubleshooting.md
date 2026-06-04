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
| Job already running toast | Concurrent `POST …/execute` | `gui_job.json` `status: running` | Wait for job poll; open **Logs** |
| QC fail with no guidance | Strict narrative/EDL QC | `run_meta.qc_summaries` | Read errors in gate panel; **View Logs**; **Redo from selected stage** |

---

## Pipeline / CLI

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| Stage skipped unexpectedly | `.stage_done/` marker present | `.stage_done/<stage>` | Delete marker for that stage **and** downstream only if you intend re-run; or use `--from-stage` |
| `run_analysis.py` stops mid-run | Gate G0 or `needs` in envelope | `transcript/review_queue.json`, `gui_log.jsonl`, `understanding/stage_runs/.../attempt_*.json` | Complete G0; fix `needs` per envelope |
| Wrong run directory | `--run-id` mismatch | `run_meta.json` | Pass correct `--run-id` / execution folder |

---

## LLM artifacts and validation

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| Stage output **pending** | Stage not run or persist blocked | `.stage_done/<stage>`, `gui_log.jsonl`, `understanding/stage_runs/<stage>/attempt_*.json` | Run stage; fix arbiter reject or schema errors in attempt audit |
| **partial** after stage marked done | Semantic gaps or invalid JSON on disk | File content vs [artifact-generation-and-validation.md](../cross-cutting/artifact-generation-and-validation.md) | **Fill gaps** in GUI or `--from-stage <producer>` |
| GUI save fails / schema toast | Zod or server jsonschema | Editor status lines, response `errors[]` | Fix fields; compare to `docs/cross-cutting/json-schemas/` |
| `content_brief.json` missing themes in profile | `memory_updates` not merged | Latest `content_context` attempt envelope | Re-run `content_context`; check arbiter `accept` |
| Operator themes overwritten | Profile not verified | `analysis_state.json` `meta.operator_verified` | Mark verified; re-run from stage |
| Pipeline re-runs same stage unexpectedly | Incomplete artifact guard | `artifact_completeness.should_run_stage_for_artifact` | Complete file or edit to valid shape |

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
| Invented facts | Model drift | `evidence_segment_ids`, transcript | Re-run with verified profile; tighten prompt guardrails |

---

## Audio / mix

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| No VO in `master.wav` | Missing `vo_pickup/` files, EDL gap placements, or mix skipped | `flow_1_master/edl.json`, `vo_pickup/`, `.stage_done/mix_flow1` | Match WAV filenames to `gap_report`; `--from-stage edl_flow1` then `assembly_preview`; re-run `mix_flow1` — [assembly_and_mux](../pipeline/assembly_and_mux/README.md) |
| SFX unused in master | Missing SDP assets, craft/generate not run, or empty cues | `understanding/sound_design_plan.json`, `sound_design/assets/`, `.stage_done/elevenlabs_sfx_flow1` | Re-run `sound_design_plan_flow1` → craft → generate → `mix_flow1`; verify cue `asset_id` links — [sound-design.md](../cross-cutting/sound-design.md) |
| SFX feels random | Weak palette/plan or skipped post-listen QA | SDP `coherence`, `elevenlabs_prompts.json` | Re-run `sound_design_palettes` / flow plan; enable G1.5 (`g1_5_require_prompt_approval: true`) |
| Loudness wrong | Master out of LUFS/peak spec | `verify_master.py` failure lines; re-run `master_flow*` after fix | [evaluation-metrics.md](../cross-cutting/evaluation-metrics.md) |

---

## ElevenLabs (SFX / isolation — API)

**Canonical guide:** [elevenlabs-integration-guide.md](../cross-cutting/elevenlabs-integration-guide.md). **Checklists:** [operator-stage-checklists.md § ElevenLabs](./operator-stage-checklists.md#elevenlabs-sfx--isolation).

### HTTP / API

| If you see | Meaning | Inspect | Action |
|------------|---------|---------|--------|
| `401` / `Unauthorized` | Bad or missing API key | `ELEVENLABS_API_KEY` | Fix secrets; reload env; **do not retry** |
| `429` / `rate limit` / `too many requests` | Quota or burst cap | Logs, dashboard | Backoff 2^n s (n=1..5); ≤2 parallel; serialize assets |
| `402` / payment (varies by vendor copy) | Billing / plan | ElevenLabs account | Stop generation; resolve billing |
| `5xx` / timeout | Server or network | Payload size, proxy | Retry 5s, 15s, 45s (max 3); then placeholder WAV (target) |
| Timeout / empty body | Network or large file | Isolation file duration | Retry once; for isolation use streaming/chunking when implemented |

### Quality / product

| Symptom | Likely cause | Inspect | Action |
|---------|----------------|---------|--------|
| SFX unused in master | Missing assets or mix not run | SDP `assets[]`, `sound_design/assets/`, `.stage_done/mix_flow*` | Re-run craft → generate → `mix_flow1` / `mix_flow2`; check cue `asset_id` references — [stage-registry](../build-out/stage-registry.md) |
| Random / trailer feel | Weak craft or legacy v1 brief path | SDP + `elevenlabs_prompts.json` | Default: SDP + craft; tune [prompt_influence](../cross-cutting/elevenlabs-prompt-influence-tuning.md) |
| Wrong timbre after regen | Variance or influence | `elevenlabs_prompts.json` | [Regression appendix](../prompts/_shared/examples/elevenlabs-prompt-regression.md); rewrite prompt |
| Voice in generated bed | Weak craft | `elevenlabs_prompts.json` | Regen; strengthen `negative_prompt`; block policy strings |
| Bed buries speech | Level / duck too hot | SDP cues `level_db`, `duck_under_speech_db` | Post-gen: lower bed −4 dB or duck +4 dB — [sound-design.md](../cross-cutting/sound-design.md) |
| Harsh montage cuts | Fixed concat / no crossfade | Flow 2 selection ranks | Post-gen: 80–200 ms crossfade; lower transition level |
| Isolation underwater | Over-processing | A/B raw vs `preclean/isolated.wav` | Disable pre-clean; try `rnnoise_local` |
| Cost spike | Per-cue v1 or regen loop | # API calls vs unique `asset_id`s | Enforce reuse; idempotent skip; G1.5 approval |
| Regen loop | Plan hash not updating | SDP + `elevenlabs_prompts.json` | Fix craft; cap 2 regens per asset |

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
