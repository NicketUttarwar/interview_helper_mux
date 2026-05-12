# interview_helper_mux

Design notes and specs for **one long interview recording → analyzable text, ranked segments, optional edits, and a muxed podcast-style master** (personal / single-operator use). **`docs/` is the source of truth** for product behavior and pipeline vocabulary; the repo also ships **early Python**: file-backed secrets (`mux_secrets`), OpenAI / AWS / ElevenLabs adapters, an SQLite **`mux_store`** (schema + doc sync + runtime helpers), and smoke CLI scripts under `tools/`.

---

## At a glance

| | |
|--|--|
| **Goal** | Re-order, trim, bridge, process, and master using **audio + transcripts + manifests**—not re-interviewing—unless you explicitly add synthetic lines. |
| **Where to start** | [docs/INDEX.md](docs/INDEX.md) · [docs/README.md](docs/README.md) |
| **End-to-end stories** | [docs/execution/README.md](docs/execution/README.md) |
| **Orchestration vs components** | [docs/execution/orchestration-component-map.md](docs/execution/orchestration-component-map.md) |

---

## Repository structure (high level)

```text
interview_helper_mux/
├── README.md                      ← this file (keep short; edit as the repo grows)
├── config/
│   ├── app.defaults.json          ← committed defaults (e.g. default SQLite path)
│   ├── templates/                 ← `secrets.env.example`, `app.defaults.json` (copy/edit locally)
│   └── secrets/                   ← gitignored; create from templates (see config/README.md)
├── ai/python/
│   ├── mux_secrets/               ← merges `config/secrets/openai.env` (optional) + `secrets.env` in memory only
│   ├── openai_mux/                ← OpenAI client, SDK major gate, prompts, `rank_segments_by_rubric`
│   ├── aws_mux/                   ← boto3 session (region + credentials from secrets file)
│   └── elevenlabs_mux/            ← ElevenLabs client (TTS / voice)
├── requirements.txt               ← preferred pip entry (`-r requirements-integrations.txt` + layout notes)
├── requirements-integrations.txt  ← pinned SDK majors: openai 2.x, boto3, elevenlabs
├── requirements-ai.txt            ← same stack as integrations (`-r requirements-integrations.txt`)
├── db/
│   ├── schema.sql                 ← DDL + FTS5 doc search
│   ├── seed_pipeline_stages.sql   ← backbone `pipeline_stage` rows
│   └── python/mux_store/          ← connect, init, sync docs, runtime helpers (see db/README.md)
├── data/                          ← default SQLite under `data/*.sqlite` (gitignored); `data/.gitkeep` tracked
├── tools/                         ← sync_to_sqlite.py, openai_smoke.py, aws_smoke.py, elevenlabs_smoke.py
└── docs/
    ├── INDEX.md           ← flat link hub
    ├── README.md          ← how to read the doc tree
    ├── execution/         ← presets, mux nightmares, automation, gating, optional ML overlays
    ├── pipeline/          ← capture → ingest → … → mastering (stage READMEs + leaf topics)
    ├── workflows/         ← loops, idempotency, parallel runs, human overrides
    ├── versions/          ← low-risk vs high-risk capability posture
    └── cross-cutting/     ← segment schema, evaluation metrics
```

Heavy assets, secrets, and generated audio stay **out of git** (see [docs/README.md](docs/README.md)). Put API keys under **`config/secrets/`** (entire tree gitignored): copy [config/templates/secrets.env.example](config/templates/secrets.env.example) to `config/secrets/secrets.env`. Optional legacy **`config/secrets/openai.env`** is merged first; duplicate keys are overridden by `secrets.env` — see [config/README.md](config/README.md).

**Integrations:** `pip install -r requirements.txt` (or `requirements-integrations.txt` / `requirements-ai.txt`), fill secrets, then run `python tools/openai_smoke.py`, `python tools/aws_smoke.py`, or `python tools/elevenlabs_smoke.py` from the repo root (scripts prepend `ai/python` to `sys.path`). Shared loader: `mux_secrets.load_repo_config()`. OpenAI prompts live under `ai/python/openai_mux/prompts/` (index: `PROMPTS_EXECUTION.txt`). Default SQLite path: `config/app.defaults.json` (`database_path`, typically `data/interview_mux.sqlite`). LLM ranking API: `openai_mux.rank_segments_by_rubric` — [docs/pipeline/scoring-and-selection/llm-assisted-ranking.md](docs/pipeline/scoring-and-selection/llm-assisted-ranking.md).

**Doc corpus in SQLite:** `python tools/sync_to_sqlite.py` creates or opens the DB, runs `mux_store.init_db` (applies `db/schema.sql` plus `db/seed_pipeline_stages.sql` when present), then syncs Markdown from `docs/` and the root `README.md` into `mux_store` — details in [db/README.md](db/README.md).

---

## Architecture (very high level)

**Single backbone** every product story still hangs on:

**capture → ingest → transcription → segmentation → scoring & selection → snippet store → audio editing → assembly & mux → mastering & export**

Human review is a **control plane** (approve, reorder, gates)—not a duplicate physics pipeline. Details per stage: [docs/pipeline/](docs/pipeline/).

---

## Orchestration ideas (very high level)

These are the **ideas** the execution docs spell out; treat this block as **summary only**—update it when presets or policy change.

1. **Frozen backbone, parameterized tools** — The orchestrator adjusts **configs and allowed tools**; it does not invent arbitrary new pipeline stages at runtime ([docs/execution/automation-and-prompt-orchestration.md](docs/execution/automation-and-prompt-orchestration.md)).
2. **Presets (“archetypes”)** — From simple **highlight reel** through **timeboxed director’s cut**, **nonlinear graph story**, **bilingual/code-switch**, **DSP polish**, **speech-to-speech**, and **custom rankers**—each is a named slice you could ship as one button ([docs/execution/complexity-ladder-end-to-end-ideas.md](docs/execution/complexity-ladder-end-to-end-ideas.md)).
3. **Difficult mux as first-class** — Bad **joins** (level, room tone, overlap, narrative whiplash) get **edge costs**, search/bridges, and human escalation when needed ([docs/execution/difficult-segment-combinations.md](docs/execution/difficult-segment-combinations.md)).
4. **High-risk gating** — First use of destructive or novel capabilities (S2S, separation, custom checkpoints, **optional** spectrogram-YOLO / Wav2Vec overlays) stops once per profile until approved ([docs/execution/high-risk-first-use-gating.md](docs/execution/high-risk-first-use-gating.md)).
5. **Optional parallel enrichments** — e.g. **spectrogram YOLO11** (hazard localization) and **Wav2Vec** embeddings (dedup / continuity hints) attach **after ingest**, feed **scoring & mux** only, and stay **versioned tool calls** ([docs/execution/spectrogram-yolo-wav2vec-orchestration.md](docs/execution/spectrogram-yolo-wav2vec-orchestration.md)).

For **which doc covers what** and **conformance** of each preset against the component library, use the map: [docs/execution/orchestration-component-map.md](docs/execution/orchestration-component-map.md).
