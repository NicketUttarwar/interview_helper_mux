# Operator gates — v2 simplified

Canonical charter: [NORTH_STAR.md](../../NORTH_STAR.md).

**Why these gates exist:** G0 protects **idea transmission** — a wrong word or mis-attributed clause at the source poisons every downstream stage (analysis, gap detection, VO, EDL) that trusts the transcript. Ship (`master_finalize` / publish) is blocked on **hard delight** — the `listen_delight_audit` floors (`mastering.listen_delight.mode: authoritative`, default) — so a master that fails the human-listen bar cannot silently go out the door. See [NORTH_STAR.md#essence](../../NORTH_STAR.md#essence) and [NORTH_STAR.md#human-listen-rubric-ship-checklist](../../NORTH_STAR.md#human-listen-rubric-ship-checklist).

## Hard gates

| Gate | ID | Behavior |
|------|-----|----------|
| **G0** | `transcript_review` | **Mandatory.** Pipeline stops after `transcript_review_build` until STT corrections are complete. Protects idea transmission: every downstream analysis/gap/VO/EDL stage trusts this text. |
| **G-Framing** | After `source_topology_build` | **Required choice (recommended default Yes).** Add interviewer framing audio (questions, summaries, prefaces, bridges) with voice-cloned least-spoken host? `POST …/gap-framing/enable`. Unattended/E2E may auto-accept via `analysis.gap_fill.auto_accept_defaults` or `INTERVIEW_MUX_AUTO_ACCEPT_GATES=1`. |
| **G-Speaker** | G-Framing = Yes | Confirm gap pickup speaker — default **least-spoken** (`PickupSpeakerPanel`). |
| **G-VoiceRef** | G-Framing = Yes | Approve collated voice reference for Chatterbox (`VoiceReferencePanel`). |
| **G-Delivery** | G-Framing = Yes | Chatterbox clone (default) or record at G1 (`GapDeliveryPanel`). |
| **G1** | `g1_vo_pickup` | **Optional.** Reachable after `gap_framing_recompose` accepts a candidate **or** skip-copies the draft — [flow integrity](../cross-cutting/refinement-passes.md) guarantees `understanding/gap_report.json` is always authoritative first. Record or synthesize gap lines, or **Skip — continue without gap VO** (`POST …/g1/skip-optional`). Batch synthesize: `POST …/g1/synthesize-all`. |

## Non-gates (optional offers)

| Offer | When | Behavior |
|-------|------|----------|
| Pre-clean source | Before ingest | Never auto-run; dismissible |
| NLE edits | After ranking / before EDL | Operator choice via Timeline tab |
| Assembly preview listen | After `assembly_preview` | Soft milestone; does not block mix by default |
| **G-Listen** | After `mix` when `master/listen_critic.json` recommends (`g_listen_recommended`) | Optional borderline quality review before `master_finalize`. Default `sound_design.g_listen_mode: warn` (advisory). Set `block` to hard-stop. Continue: `POST …/g-listen/continue`; skip: `POST …/g-listen/skip`. Distinct from `listen_delight_audit` (see below), which is the **authoritative** hard delight ship gate — G-Listen is an earlier, optional pass. |
| **Timeline optimizer** | Auto-starts after `mix` (defaults) | **Endless daemon (mode C)** permutes structure + glue + SDP + optional LLM proposals per run. GUI: Take best + remaster / Keep optimizing / Stop / Skip. Artifacts under `master/optimizer/`. Config: `mastering.timeline_optimizer`. |
| **`listen_delight_audit`** (not operator-facing) | After `assembly_preview`, before SFX craft | **Hard ship blocker, no GUI interaction.** Scores `mastering/listen_delight_audit.json` against seven delight floors; when `mastering.listen_delight.mode: authoritative` (default) a floor failure hard-stops the stage immediately and re-blocks at `post_master_quality`/publish. Set `mode: advisory` to score without blocking. See [narrative-mode-and-montage.md#listen-delight](../cross-cutting/narrative-mode-and-montage.md#listen-delight). |
| **G-Publish** | After `master_finalize` (Ship) | Optional local episode package + separate ASSETS-wide S3 sync. **Prepare package for this run:** `POST …/g-publish/continue` runs `episode_meta_build`…`podcast_publish` locally (no S3). **Upload all ready packages:** `POST …/g-publish/sync` (or `python scripts/sync_podcast_episodes.py`) uploads complete `publish/` packages under `ASSETS/executions/` — skips known `execution_id`s, never deletes S3. **Skip:** `POST …/g-publish/skip`. See [podcast-rss-hosting.md](../cross-cutting/podcast-rss-hosting.md). Note: reaching `master_finalize` already implies `listen_delight_audit` passed (authoritative mode) — Ship is not blocked again here for delight, only for the optional package/sync step. |

## Removed gates (v2)

- G0.5 `disfluency_review` (stage and panel deleted)
- `analysis_profile` / `operator_verified` profile gate
- G2 flow selection (Flow 2 / Flow 3 deleted)
- G1.5 SFX prompt approval (default off: `g1_5_require_prompt_approval: false`)
- Per-stage write approval (auto-commit artifacts)
- Custom-run handoff acks

## LLM failures

v2 uses **schema validate → one retry → hard stop** (`llm_simple.py`). The LLM-arbiter / investigation-queue UI was removed, along with shard/collate/arbiter routing — there is no alternate path when a stage fails. Re-run with `--from-stage <id>` after fixing upstream artifacts. (This concerns **LLM volley** message assembly, not **speaker volley** conversation structure — see [volley-glossary.md](../cross-cutting/volley-glossary.md).)

See [docs/v2/drop-manifest.md](../v2/drop-manifest.md).
