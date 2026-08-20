# Diarization same-speaker verify — exec_510 novel|1080

Live pair test + production follow-through for the hinge hang on *“…developed a very novel”* / *“1080 gene panel…”*.

## Fixture

Run: `ASSETS/executions/exec_510_d19c15b58ab4_20260819T212734Z`  
Source wav: `ASSETS/input/mohan_uttarwar_podcast_transforming_cancer_science_direct.wav`

| Side | Segment | Source times | Words | Shipped `speaker_id` |
|------|---------|--------------|-------|----------------------|
| A (pre) | `seg_016` end | **novel** `1785000–1785600` | *“…developed a very novel”* | `spk_1` |
| gap | | **1120ms** (under the 4s ceiling) | | |
| B (post) | `seg_017` start | **1080** `1786720–` | *“1080 gene panel that works on the liquid…”* | `spk_0` |

Clips cut for the test: A `1781600–1785600` (~4s ending on *novel*), B `1786720–1790720` (~4s from *1080*), concat with 300ms silence. Workdir: `ASSETS/local_speech/pair_test_novel_1080/` (`result.json`).

## Did preload + interrogate run?

| Step | Ran? | Notes |
|------|------|--------|
| ffmpeg clips | **Yes** | Both wavs + concat wrote successfully |
| Speech venv `s2s_interrogate --verify` | **Yes** | mlx-audio **0.2.10** — modes warmup/classify only; **no** `mlx_audio.vad` |
| S2S warmup (spoken YES/NO instruction) | **No** | Qwen3-TTS fetch completed, then `Model type qwen3_tts not supported` on 0.2.10 `tts.generate` |
| STT listen of each clip | **Yes** | Whisper turbo. A: *“section of the test where we have developed a very”* (dropped the last word *novel*). B: *“1080 gene panel that works on the liquid”*. STT text is **not** an identity verdict. |
| Sortformer identity | **Yes** (sidecar) | Production speech venv cannot import `mlx_audio.vad`. Sidecar **mlx-audio 0.4.8** loaded `mlx-community/diar_sortformer_4spk-v1-fp32` and labeled the concat. |

## Verdict

**YES — same speaker.** Original diarization was wrong to split `spk_1` → `spk_0` at this seam.

Raw Sortformer (trimmed):

```
SPEAKER audio 1 0.690 3.360 speaker_0
SPEAKER audio 1 4.450 2.000 speaker_0
SPEAKER audio 1 7.010 1.360 speaker_0
```

Segments (concat 8.3s; join at 4.3s): `speaker 0` `0.69–4.05`, `4.45–6.45`, `7.01–8.37`. One ID on both sides of the silence. Split at 4.3s sits in the 4.05–4.45 pause (the inserted 300ms).

## Implication

Stage 2 (4s same-clause window + fuse + relabel + metadata) **is justified** for this seam. Production hinge + fail-open verify path is in the repo (see plan file). Live Sortformer identity needs mlx-audio **≥ 0.4.8**; the shipped speech venv is **0.2.10**, so runtime pair-verify **fail-opens** (keeps labels) until that venv is upgraded. The unfinished-nominal hang still forbids a keeper end on *a very novel* even when verify misses.

## Stop

Do not patch `transcript/full.json` on exec_510 from this report. A later pipeline run after G0 will apply relabel only when `speaker_pair` returns YES from a venv that has Sortformer.
