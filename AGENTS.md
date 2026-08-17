# Agent guide — interview_helper_mux (v2)

**North star:** [NORTH_STAR.md](NORTH_STAR.md) — messy interview → structured **`master/master.wav`** (golden nuggets, ideal cuts, native↔synthetic↔sonic conversation; **authoritative listen-delight** ship gate).

**Operator flow:**

```bash
./scripts/bootstrap_venv.sh   # once
./scripts/run.sh              # launch GUI
```

**Pipeline size:** **65 stages** — 34 analysis + 31 delivery — [`src/interview_mux/v2/config.py`](src/interview_mux/v2/config.py) · [docs/v2/port-manifest.csv](docs/v2/port-manifest.csv).

## Read order

1. [NORTH_STAR.md](NORTH_STAR.md)
2. [docs/cross-cutting/mastering-process.md](docs/cross-cutting/mastering-process.md) — **unified strategy** for final master construction (TBIY is heritage only)
   - [docs/cross-cutting/narrative-mode-and-montage.md](docs/cross-cutting/narrative-mode-and-montage.md) — narrative_mode, montage grammar, two-pass Shape, FT
   - [docs/cross-cutting/mastering-quality-hardening.md](docs/cross-cutting/mastering-quality-hardening.md) — reliability gates layered on that strategy
3. [docs/cross-cutting/volley-glossary.md](docs/cross-cutting/volley-glossary.md) — **speaker volley** vs **LLM volley**
   - [docs/cross-cutting/llm-volley-context.md](docs/cross-cutting/llm-volley-context.md) — tape-only LLM packets; metadata denylist
4. [docs/workflows/operator-journey.md](docs/workflows/operator-journey.md)
5. [docs/workflows/operator-gates.md](docs/workflows/operator-gates.md)
6. [docs/v2/port-manifest.csv](docs/v2/port-manifest.csv)
7. [docs/cross-cutting/local-audio-stack.md](docs/cross-cutting/local-audio-stack.md)
8. [docs/cross-cutting/podcast-rss-hosting.md](docs/cross-cutting/podcast-rss-hosting.md) — The War Room S3 + CloudFront RSS (optional Ship)
9. [terraform/README.md](terraform/README.md) — Terraform wrappers, committed state, session backup; app AWS via **boto3** + `secrets.env` — never AWS CLI / `aws login`
10. [docs/cross-cutting/podcast-cover-theme.md](docs/cross-cutting/podcast-cover-theme.md) — OpenAI cover cascade (3-candidate + vision brilliance pick)
11. [docs/cross-cutting/anchored-toolchain.md](docs/cross-cutting/anchored-toolchain.md) — pins; AWS = Terraform + boto3
12. [docs/workflows/api-reference.md](docs/workflows/api-reference.md)
13. [docs/cross-cutting/timeline-optimizer.md](docs/cross-cutting/timeline-optimizer.md) · [stage-volley-matrix.md](docs/cross-cutting/stage-volley-matrix.md) · [episode-architecture-spine.md](docs/cross-cutting/episode-architecture-spine.md)
