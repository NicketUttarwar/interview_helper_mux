# Agent guide — interview_helper_mux (v2)

**North star:** [NORTH_STAR.md](NORTH_STAR.md) — messy interview → structured **`master/master.wav`** (golden nuggets, ideal cuts, native↔synthetic↔sonic conversation; **authoritative listen-delight** ship gate).

**Operator flow:**

```bash
./scripts/bootstrap_venv.sh   # once
./scripts/run.sh              # launch GUI
```

**Pipeline size:** **72 stages** — 35 analysis + 37 delivery — [`src/interview_mux/v2/config.py`](src/interview_mux/v2/config.py) · [docs/v2/port-manifest.csv](docs/v2/port-manifest.csv) (76 manifest rows incl. aliases/retired).

**Brains:** Start-tab slider. **0.2.0** (default — latest registered) fixed seed-order homunculus walk. **0.0.0** original linear walk remains available. Canon: [docs/cross-cutting/mastering-homunculus.md](docs/cross-cutting/mastering-homunculus.md).

**Full-auto forensics (debug campaign):** [.cursor/plans/full_auto_forensics_run.plan.md](.cursor/plans/full_auto_forensics_run.plan.md) — **always kick off FRESH** (`MUX_FRESH=1`, new `exec_*`; never prior execution folders). On bugs: diagnose → cascade pytest (`MUX_FORENSICS=0`) → patch code → continue that same run_id (`MUX_FRESH=0`); log intervenes for later review — do **not** map to predicate-family / End-* ledgers mid-run. Parent must arm **§3.0a `AGENT_LOOP_TICK_forensics` every 4m** (`notify_on_output`). State: [.cursor/plans/full_auto_forensics_state.md](.cursor/plans/full_auto_forensics_state.md). Do **not** spawn a second fresh exec mid-campaign to verify a late-stage fix. Optional post-ship tape acceptance: plain full-auto with `MUX_FORENSICS` unset (§2.1).

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
14. [docs/cross-cutting/air-order-boundary.md](docs/cross-cutting/air-order-boundary.md) — federated air-order constitution, checkpoints, lifecycle bus
15. [docs/cross-cutting/artifact-ownership.md](docs/cross-cutting/artifact-ownership.md) — **ALLOW/DENY ownership SSOT** (`artifact_ownership.py`); new `write_json` / stage / `from_stage` / GUI route needs an ALLOW row in the same change
