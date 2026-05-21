# Interview helper (documentation)

**Scope:** Personal, individual use—one operator, local design and tooling for turning long interview recordings into analyzable text, ranked segments, optional cuts, and a composable podcast-style master.

This folder is the **source of truth** for components and ideas. Each markdown file should stay **one concern**; use [INDEX.md](INDEX.md) to navigate.

## How to read the tree

1. **[execution/](execution/)** — End-to-end presets: start with [orchestration-component-map.md](execution/orchestration-component-map.md) (**library review** for A–K), then ladder, difficult joins, automation, **first-use gating** for high-risk tools, S2S / training notes, optional spectrogram / Wav2Vec overlays, [full localized dub](execution/full-localized-dub-orchestration.md) (translate + voice clone → new-language master).
2. **[versions/](versions/)** — Two product tiers: **low-risk** (simple, managed APIs) and **high-risk** (ensembles, custom models, speech-to-speech, many providers).
3. **[pipeline/](pipeline/)** — Ordered stages from capture through export; each stage has a `README.md` and leaf topics.
4. **[workflows/](workflows/)** — Non-waterfall patterns: loops, idempotency, parallel candidates, human overrides.
5. **[cross-cutting/](cross-cutting/)** — Shared data shapes and how you measure quality.

Conventions for leaf files: optional YAML frontmatter (`id`, `tier`, `status`, `depends_on`); end with **Open decisions** and **Links** where helpful.

## Repository code

Python **3.12** pipeline and store code live at repo root (`pipeline/`, `db/python/mux_store/`, `ai/python/`). Install and gates: **[SETUP.md](../SETUP.md)**. Heavy audio assets and secrets stay out of git.
