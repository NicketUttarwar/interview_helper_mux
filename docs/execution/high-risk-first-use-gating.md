---
id: execution-high-risk-gating
tier: both
status: spec
depends_on: [execution-readme]
---

# High-risk first-use gating

**Policy:** the run stays **hands-off** until the orchestrator is about to call a **high-risk** capability that has **not** yet been approved for this **profile** (or this machine). Then it **stops and asks once**, with a clear summary of cost, side effects, and artifacts.

## What is **not** gated

- **Baseline room DSP** (noisereduce + pedalboard) on the final master — **mandatory** in preset A and always on. See [project north star](../../.cursor/rules/project-north-star.mdc).

## What counts as “new tool”

Examples you might tag as high-risk (your list can differ):

- First use of a **speech-to-speech** or **voice conversion** adapter on real interview audio.
- First use of a **custom fine-tuned** scorer or **local LoRA** not shipped with the repo default.
- First use of **source separation** that will permanently alter archived stems.
- First outbound call to a **new vendor** not on an allowlist.
- First use of **spectrogram YOLO11** or **Wav2Vec** inference with **custom weights / checkpoints** not in the repo default ([spectrogram-yolo-wav2vec-orchestration.md](spectrogram-yolo-wav2vec-orchestration.md)).

## Gate payload (what the user sees)

- **Tool id** + version hash.
- **Inputs:** which `session_id`, which `segment_id`s or time ranges.
- **Estimated cost** (API $, GPU minutes).
- **Irreversible?** (e.g. destructive overwrite of golden master).
- **Undo:** what snapshot or manifest rollback restores.

## After approval

- Store `approved_tools[tool_id] = version_hash` in local profile (gitignored JSON is fine).
- Subsequent fully automatic runs may call it without asking until version changes.

## Open decisions

- Whether **version bump** always re-opens the gate (recommended for safety).

## Links

- [../versions/high-risk.md](../versions/high-risk.md)
- [orchestration-component-map.md](orchestration-component-map.md)
- [speech-to-speech-and-trained-remix-models.md](speech-to-speech-and-trained-remix-models.md)
- [spectrogram-yolo-wav2vec-orchestration.md](spectrogram-yolo-wav2vec-orchestration.md)
- [automation-and-prompt-orchestration.md](automation-and-prompt-orchestration.md)
