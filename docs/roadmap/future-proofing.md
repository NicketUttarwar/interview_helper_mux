# Future-proofing — guardrails for analysis & features

Lightweight rules and **small idea directions** for future work. Does not replace [pipeline.md](../pipeline.md), [build-out/README.md](../build-out/README.md), [build-out/steps-forward.md](../build-out/steps-forward.md), or implementation specs.

## Guardrails

**Toolchain:** New dependencies must use the [anchor lock](../cross-cutting/anchored-toolchain.md) (`requirements.lock`), pass `pip-audit` at setup, and be documented with exact versions. Code agents use **Context7** at those pins.

**Optimize for (when adding analysis or product features):**

| Axis | Ask |
|------|-----|
| **LEX** — listener | Would a stranger stay engaged and trust the audio? |
| **COM** — ideas | Would they leave with the right concepts, not just keywords? |
| **CRE** — operator | Does this give faster confidence or better options than text alone? |

**Do not treat as the main driver:** “fix v1 first,” backwards-only gap audits, deployment/hybrid debates, or **video / computer vision** (no CV, no YOLO-class tooling). This pipeline is **audio + transcript text** unless the product explicitly expands scope elsewhere.

**Spikes:** time-box experiments; record outcomes in [spike-results-and-winners.md](../pipeline/value-analysis/spike-results-and-winners.md). **`ON`** = shipped in code and used on a default or flagged operator path — note it here when true.

## Idea directions (optional R&D)

Condensed themes (add rows sparingly). Tier: **T0** quick try, **T1** new artifact/UI, **T2** heavy bet.

| Area | Direction | Tier |
|------|-------------|------|
| Ingest / STT | SSL or quality curves for “idea density” / trust dips, not only word confidence | T0 |
| Ingest / STT | Multitrack hints for speaker attribution before roles | T0 |
| G0 | Review queue ranked by communicative salience, not confidence alone | T0 |
| Understanding | Prosody / overlap signals to enrich beats and roles — **Spec:** [source-derived-sonic-mix-profile.md](../cross-cutting/source-derived-sonic-mix-profile.md) | T0–T1 |
| Segmentation | Audio + text boundaries (e.g. SSL states), not only pause heuristics | T0 |
| Gaps / VO | Listener comprehension risk + VO ranked by retell uplift | T0–T1 |
| Flow 1 narrative | Pacing + lexical signals for order and transitions — **Spec:** [source-derived-sonic-mix-profile.md](../cross-cutting/source-derived-sonic-mix-profile.md) | T1 |
| Flow 1 sound | CLAP-style semantic retrieval; events (laughter) for sting safety | T1 |
| Flow 1/2 sound | ElevenLabs craft + post-gen placement — [elevenlabs-integration-guide.md](../cross-cutting/elevenlabs-integration-guide.md) (docs shipped); per-run mix baseline — [source-derived-sonic-mix-profile.md](../cross-cutting/source-derived-sonic-mix-profile.md) | T1 |
| Flow 2 | Audio–text retrieval + hook-first acoustic cues | T0–T1 |
| Memory | Chunked audio + text spine; investigations on acoustic + text surprise | T1–T2 |
| Program-wide | Audio LM “confusion map” (only with governance) | T2 |

## Optional detail

Rubrics, moonshot model families, templates, per-stage notes: [pipeline/value-analysis/README.md](../pipeline/value-analysis/README.md).

## Shipped signals (`ON`)

| Capability | ON |
|------------|-----|
| G1.5 prompt review gate (`g1_5_require_prompt_approval`) | Yes — GUI + API + `g15_prompt_review.py` (shipped default **on**) |
| Value-analysis spike scoring CLI | Yes — `tools/run_value_spike.py` (**tooling only**; not a separate pipeline stage) |
| Value-features extractor CLI | Yes — `tools/extract_value_features.py` → `understanding/value_features.json` |
| Value-features auto-extract after `content_context` | Yes — `value_analysis.auto_extract_after_content_context` (shipped default **on**; hook in `understanding.run_content_context`) |
| Stage enrichment signals in LLM context | Yes — `stage_enrichment.py` → `pause_ladder_hints`, `emphasis_regions`, `quotability_signals`, `value_features_summary` |
| Specialist orchestration loop | Yes — `analysis.specialists.enabled` (shipped default **on**) |
| Show description evidence QC | Yes — `show_description_qc.py`, `tools/validate_show_description.py`, `show_description_qc.strict` |
| Primary LLM `json_object` response format | Yes — all primary/shard/collate/specialist calls in `llm_runner.py` |

Update this table when a future-proofed capability lands in the app.
