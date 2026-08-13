# Local audio stack (DeepFilterNet + MusicGen + MMAudio)

Interview MUX runs **noise reduction** and **theme music generation** locally via isolated venvs under `ASSETS/`. No ElevenLabs API keys or cloud audio spend. STT and diarization are likewise local (MLX, `ASSETS/local_speech/venv`) — AWS Transcribe was removed.

**Source audio:** Non-WAV drops under `ASSETS/` (mp3, mp4, m4a, flac, …) are converted once to a sibling `.wav` (`ffmpeg` → `pcm_s16le`, video stripped) on run init / `input_audio()`. DeepFilter and the rest of the pipeline always read that WAV; `run_meta.input_audio_path` points at it (`input_audio_path_original` keeps the operator file when converted).

| Tool | Upstream | Stage use | Venv |
|------|----------|-----------|------|
| DeepFilterNet | DeepFilterNet | preclean | `ASSETS/local_deepfilter/venv` |
| **MusicGen** | facebook/musicgen-large (+ ladder → medium → small; melody-large optional) | creative-delivery `theme_*` stems | `ASSETS/local_musicgen/venv` (`./scripts/bootstrap_musicgen.sh`) |
| MMAudio | [hkchengrex/MMAudio](https://github.com/hkchengrex/MMAudio) | legacy / non-creative SFX only (disabled for show path when MusicGen enabled) | `ASSETS/local_mmaudio/venv` |

**Music-only rule:** creative delivery never ships whoosh/tick/foley/murmur. A **fixed palette** (motif, underscore_loop, optional_loop, stingers, 1–2 full beds) shares motif DNA (`understanding/music_brief.json` + SDP `motif_family`). `music_palette_compose` places/reuses those assets into the master cue timeline after assembly preview. QA failure → regen → fallback to a passed stem in the same family → else fail-closed.

**MusicGen resources:** Default device is **`auto`** — prefers **MPS** on Apple Silicon (or CUDA when present), else CPU. PyTorch **MPS** can still `abort()` inside Metal (`MTLReportFailure` / `Python quit unexpectedly`). After a SIGABRT the runner bans MPS for the rest of the run and retries once on CPU (`ban_mps_on_abort`). Generation is serialized via the machine-wide **`local_gpu`** gate (shared with Chatterbox / MMAudio / MLX / DeepFilter) and launched via the framework CLI `python3.12`, not `Python.app`. After each GPU subprocess exits, **`cooldown_sec` (default 5)** elapses before the next consumer may start. `PYTORCH_ENABLE_MPS_FALLBACK=1` is set for missing Metal ops.

**Model ladder (large first):** `musicgen-large` → `musicgen-medium` → `musicgen-small` (same prompt + planned duration), then **MMAudio** backup, then a deterministic musical-note stub. MusicGen **always** runs this ladder first (including unattended e2e — there is no fast-stub skip). `prefer_medium_on_cpu` defaults **false**. Step-downs stay on the same accelerator (MPS/CUDA); CPU is only used when device resolves to cpu or after an MPS abort retry. `request_timeout_sec` (default **900**) is hang safety for the primary on GPU; `cpu_request_timeout_sec` is tighter so CPU thrash steps down. `fail_closed_on_stub` defaults **false** so last-resort audio still reaches mix after the ladder.

**Local runtime JSON:** scripts emit one JSON object on stdout `{ok, error?, out_wav?, warnings?}`. Progress stays on stderr. `run_runtime_json` parses stdout then stderr, logs `gui_log` + `vo_pickup/local_runtime_last_error.json` with `likely_cause`. G1 synthesize-all collects per-line errors instead of aborting the batch.

**Planned:** deeper ML speech-to-speech voice conversion — [speech-to-speech-vo.md](./speech-to-speech-vo.md). DSP timbre match for operator gap VO is shipped.

## Components

| Stack | Upstream | Purpose | Venv |
|-------|----------|---------|------|
| DeepFilterNet | [rikorose/deepfilternet](https://github.com/rikorose/deepfilternet) | Optional `audio_preclean` noise reduction | `ASSETS/local_deepfilter/venv` |
| MMAudio | [hkchengrex/MMAudio](https://github.com/hkchengrex/MMAudio) | `mmaudio_sfx` text-to-audio | `ASSETS/local_mmaudio/venv` |

Weights for MMAudio are downloaded by the upstream package on first generation (HF; CC-BY-NC 4.0).

## Bootstrap (single entry)

```bash
./scripts/bootstrap_venv.sh
./scripts/verify_local_models.sh
```

This creates the core `.venv`, clones both upstream repos, builds isolated venvs, and runs verify gates.

**Requires Rust** (`rustc`) for DeepFilterNet's native `pyDF` build. Without Rust, MMAudio still bootstraps; preclean falls back until Rust is installed and bootstrap re-run.

Manual steps:

```bash
./scripts/clone_local_audio_repos.sh
bash scripts/lib/bootstrap_local_runtimes.sh
./scripts/verify_local_models.sh
```

## Verify

```bash
ASSETS/local_deepfilter/venv/bin/python scripts/download_deepfilter.py --verify
ASSETS/local_mmaudio/venv/bin/python scripts/download_mmaudio.py --verify
```

Each stack writes `ASSETS/local_*/install.json` with repo commit, venv path, and `verified_at`.

## Runtime tools

| Script | Invoked by |
|--------|------------|
| `tools/deepfilter_enhance.py` | `deepfilter_runner.enhance_wav` |
| `tools/mmaudio_generate.py` | `mmaudio_runner.generate_text_to_audio` |

## Existing runs (migration)

Runs that completed under old stage ids (`mmaudio_sfx_flow*`) are **not** auto-migrated. Re-run from `sfx_prompt_craft` after approving `sound_design/sfx_prompts.json`.

## Prompt architecture (MMAudio SFX)

| Stage | Output | Consumed by |
|-------|--------|-------------|
| `sound_design_palettes` | coherence, palettes | plan stages |
| `sound_design_plan/2` | `assets[]`, cues, optional `generation_notes` | `sfx_prompt_craft` |
| `sfx_prompt_craft` | `sound_design/sfx_prompts.json` (positive + negative + optional CFG) | `mmaudio_sfx` |
| `sfx_prompt_refine` | merged prompt rows for failed assets (optional) | regen via `mmaudio_sfx` |
| `mmaudio_sfx` | WAVs + `mmaudio_qa.json` | mix via `placement_adjustments` |

Tuning: [mmaudio-prompt-tuning.md](./mmaudio-prompt-tuning.md) · Regression: [sfx-prompt-regression.md](../prompts/_shared/examples/sfx-prompt-regression.md).

### Tier-2 semantic QA (CLAP)

When `mmaudio.semantic_qa_enabled` is `true` (shipped default), `mmaudio_qa` invokes `tools/clap_similarity.py` inside the MMAudio venv (`transformers` + `librosa` from `requirements-local-mmaudio.txt`). First run downloads `laion/clap-htsat-fused` from Hugging Face. Fail-open: missing deps or timeouts set `semantic_qa_verdict=skipped` without blocking generation. Set `semantic_qa_enabled: false` to skip Tier-2 entirely.

| Config key | Default | Role |
|------------|---------|------|
| `semantic_qa_threshold` | `0.18` | Cosine similarity pass floor |
| `semantic_qa_fail_on_low` | `false` | When true, sub-threshold scores fail QA |
| `semantic_qa_timeout_sec` | `120` | Per-asset subprocess timeout |

Re-run `./scripts/bootstrap_venv.sh` (or pip install the MMAudio requirements file) after pulling CLAP deps.

## Troubleshooting

| Issue | Action |
|-------|--------|
| `Missing venv python` | Re-run `./scripts/bootstrap_venv.sh` |
| DeepFilter `maturin` failure | Install Rust toolchain; ensure repo cloned |
| `pip install -e` flat-layout error on repo root | Bootstrap installs `DeepFilterNet/DeepFilterNet` subpackage, not repo root — re-run `./scripts/bootstrap_venv.sh` |
| `torchaudio.backend` import error | Mismatched torch/torchaudio — bootstrap pins `2.5.1` for deepfilter venv |
| MMAudio demo fails | Confirm `ASSETS/local_mmaudio/MMAudio/demo.py` exists after clone |
| Preclean falls back to `ffmpeg_local` | DeepFilter stack unavailable; check `preclean/provider.json` |

See also [SETUP.md](../../SETUP.md) § Local audio stack.
