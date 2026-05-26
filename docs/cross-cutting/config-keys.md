# Config keys — `app.defaults.json` and overrides

Authoritative defaults live in **`config/app.defaults.json`**. At runtime, `interview_mux.config.merged_config()` merges **`config/secrets/secrets.env`** (never commit secrets). This doc lists **meaningful keys**, what uses them, and **what breaks if wrong**.

---

## Top-level

| Key | Used by | If wrong |
|-----|---------|----------|
| `assets_root` | `RunContext`, GUI assets list | Wrong folder for audio discovery |
| `input_audio_path` | CLI / tools default input | Analysis points at missing file |
| `data_root` | Legacy runs `data/run_NNN` | Legacy paths broken |
| `executions_root` | New runs under `ASSETS/executions/...` | Runs created outside expected tree |
| `sample_rate` | Ingest / mastering expectation | Wrong SR → Transcribe or mux issues |
| `flow1_target_lufs` / `flow2_target_lufs` | Mastering targets (when enforced) | Wrong loudness “sound” |
| `web_port` | `serve` / `run.sh` | GUI on wrong port / collision |
| `models.<stage_key>` | `get_model()` → OpenAI calls | Wrong model: cost/quality drift; unknown name → API errors |

**Secrets override (not in JSON):** `INPUT_AUDIO_PATH` in `secrets.env` replaces `input_audio_path` — see `merged_config()`.

**Optional secrets (fallback):** `OPENAI_MODEL` used when a stage key is missing from `models` map.

---

## `analysis.max_iterations_per_stage`

Orchestrator inner loop per LLM stage. **Too low:** exits before fixing validation errors. **Too high:** extra cost on stuck stages.

---

## `analysis.max_queue_drains_per_stage`

Drains `investigation_queue` suggestions per stage. **Too low:** unresolved investigations pile up. **Too high:** thrash / cost.

---

## `analysis.context.*`

Consumed by `context_volley` shaping. See [long-interview-chunking.md](../workflows/long-interview-chunking.md).

| Key | If wrong |
|-----|----------|
| `transcript_excerpt_chars` | Truncated evidence in mid-pipeline stages |
| `transcript_full_chars` | Early understanding/segmentation blind past cutoff |
| `segment_text_max_chars` | Gap text unreadable / over-truncated |
| `max_segments_in_context` | Tail segments invisible to ranking-like stages |
| `max_segments_in_gap_pass` | Gap pass misses part of timeline |
| `max_gap_evaluations` | Some segments never evaluated in one pass |
| `max_stage_data_chars` | Huge payloads rejected or truncated by model host |
| `interviewer_sample_lines` | Transitions stage lacks tone reference |

---

## `analysis.prompt_thresholds.*`

Injected into prompts / STT prep; changing them changes **editorial behavior**, not just formatting.

| Key | If wrong |
|-----|----------|
| `pause_split_ms` | Too small → fragment boundaries; too large → merges distinct ideas |
| `short_question_max_words` | Mis-splits Q+A pairs in boundary prompt |
| `interviewer_question_max_words` / `interviewer_setup_max_words` | VO lines too long for product spec |
| `highlight_setup_max_sec` | Flow 2 clip + VO timing invalid vs schema |
| `max_chapters` | Narrative plan violates cap → validation / model confusion |
| `max_highlight_clips` | Selection over cap (should match product ≤5) |

---

## `_comment`

Documentation only — not read by code.

---

## `secrets.env` keys (merged, not in `app.defaults.json`)

Loaded by `load_secrets()` / `merged_config()`. **Never commit** real values.

| Key | Effect if wrong / missing |
|-----|---------------------------|
| `INPUT_AUDIO_PATH` | Overrides `input_audio_path` — wrong path → ingest fails |
| `OPENAI_API_KEY` | LLM stages fail at runtime |
| `OPENAI_MODEL` | Fallback when `models.<stage>` missing |
| `OPENAI_SPEECH_MODEL` | Reserved for future OpenAI audio adapters |
| `AWS_DEFAULT_REGION` / `AWS_REGION` | Transcribe / S3 wrong region |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_PROFILE` | Auth failures — see troubleshooting |
| `AWS_S3_BUCKET` / `AWS_S3_INPUT_KEY` / `AWS_S3_URI` | Transcribe cannot read media |
| `ELEVENLABS_API_KEY` | SFX + future isolation fail |

Optional placeholders in `config/templates/secrets.env.example` (AssemblyAI, Deepgram, etc.) are **not wired** until an adapter exists — document when adding code.

---

## Related

- [model-routing.md](./model-routing.md) — model tier guidance
- [prompts/README.md](../prompts/README.md) — prompt conventions
- `src/interview_mux/config.py` — merge rules
- `config/templates/secrets.env.example` — secret key names
- [../config/README.md](../config/README.md) — resolution order
