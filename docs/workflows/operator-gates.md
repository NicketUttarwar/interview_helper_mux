# Operator gates — v2 simplified

**0.0.0:** these gates behave as today. **0.1.0 (default):** the homunculus is the gate controller (categories); G0 word-level still requires a human when open. See [mastering-homunculus.md](../cross-cutting/mastering-homunculus.md).

**Why these gates exist:** G0 protects **idea transmission** — a wrong word or mis-attributed clause at the source poisons every downstream stage (analysis, gap detection, VO, EDL) that trusts the transcript. Ship (`master_finalize` / publish) is blocked on **hard delight** — the `listen_delight_audit` floors (`mastering.listen_delight.mode: authoritative`, default) — so a master that fails the human-listen bar cannot silently go out the door. See [NORTH_STAR.md#essence](../../NORTH_STAR.md#essence) and [NORTH_STAR.md#human-listen-rubric-ship-checklist](../../NORTH_STAR.md#human-listen-rubric-ship-checklist).

## Resilience escalations (quality-first)

Product stages record bounded repairs in `operator/resilience_report.json` and open structured cards under `operator/escalations/{stage}.json` when attempts are exhausted. GUI surfaces open escalations on the phase banner; resolve via `POST /api/runs/{id}/escalations/{stage}/resolve` with a documented option (`retry_stage`, `skip_optional_vo`, `prepare_local_package_only`, …).

**Never auto-published (Manual GUI):** `force_publish` / `soft_ship` / quality waivers are rejected from the interactive operator path. Soft e2e ship remains opt-in via `INTERVIEW_MUX_E2E_SOFT=1` only — enabled automatically when launching **Full-auto** from the GUI Start page or `./scripts/run.sh` (legacy `MUX_BABA_E2E=1` still accepted). Full-auto heal/remutates/re-executes with soft waivers, and logs each choice as `[DECISION major|minor]` in `ASSETS/full_auto_console.log`.

**Partially accelerated (GUI):** Uses the same detached driver and gate auto-accept stack as Full-auto, but **never** auto-accepts G0 (`transcript_review`) or uploads to S3. The operator must complete transcript review and confirm G-Publish upload (or skip). A GUI overlay blocks mis-clicks during automated phases.

Delivery helpers (G1 pickups, archive restore, resume suggestion): `POST /api/runs/{id}/delivery/recover` and `GET /api/runs/{id}/resilience`.

## Hard gates

| Gate | ID | Behavior |
|------|-----|----------|
| **G0** | `transcript_review` | **Mandatory.** Pipeline stops after `transcript_review_build` until STT corrections are complete. Protects idea transmission: every downstream analysis/gap/VO/EDL stage trusts this text. |
| **G-Framing** | After `source_topology_build` | **Required choice (recommended default Yes).** **Authority (2M):** operator **Yes/No** owns the binary synthetic-VO path (Layer 1) — sticky; Full-auto and `auto_accept_defaults` must **never** overwrite an explicit operator **No** or **Yes**. Homunculus **0.1.0** runs advisory `framing_posture_decide` before gap work; its `recommended_framing` (`yes` / `no` / `sparse`) is shown in the G-Framing panel as an LLM hint only. When G-Framing is **Yes**, LLM stages (`nugget_layup_compose`, `vo_line_adjudicate`, intro mint) are **authoritative for line text** (Layers 2–3). Homunculus **0.1.0** auto-resolves **Yes** for hosted 1:1 and multi-speaker tapes when the operator has not chosen yet (clone = frame / question-density host, never the guest). Skip only true monologue or an explicit operator **No**. `POST …/gap-framing/enable`. Unattended/E2E may also auto-accept via `analysis.gap_fill.auto_accept_defaults` or `INTERVIEW_MUX_AUTO_ACCEPT_GATES=1`. Min cloned lines (`min_synthetic_vo_lines`, default 3) is a **post-layup / EDL** ship bar, not a compose deadlock. |
| **G-Speaker** | G-Framing = Yes | Confirm gap pickup speaker — default **least-spoken** (`PickupSpeakerPanel`). |
| **G-VoiceRef** | G-Framing = Yes | Approve collated voice reference for Chatterbox (`VoiceReferencePanel`). |
| **G-Delivery** | G-Framing = Yes | Chatterbox clone (default) or record at G1 (`GapDeliveryPanel`). |
| **G1** | `g1_vo_pickup` | **Optional.** Reachable after nugget layups publish `gap_report` and/or `gap_framing_recompose` accepts/skip-copies — [flow integrity](../cross-cutting/refinement-passes.md) guarantees `understanding/gap_report.json` is authoritative. Expect **more/longer before-VO lay-ups** recovering excluded-tape facts ([nugget-layup-system.md](../cross-cutting/nugget-layup-system.md)). Record or synthesize gap lines, or **Skip — continue without gap VO** (`POST …/g1/skip-optional`). Batch synthesize: `POST …/g1/synthesize-all`. |

## Non-gates (optional offers)

| Offer | When | Behavior |
|-------|------|----------|
| Pre-clean source | Before ingest | Never auto-run; dismissible |
| NLE edits | After ranking / before EDL | Operator choice via Timeline tab |
| Assembly preview listen | After `assembly_preview` | Soft milestone; does not block mix by default |
| **G-Listen** | After `mix` when `master/listen_critic.json` recommends (`g_listen_recommended`) | Optional borderline quality review before `master_finalize`. Default `sound_design.g_listen_mode: warn` (advisory). Set `block` to hard-stop. Continue: `POST …/g-listen/continue`; skip: `POST …/g-listen/skip`. Distinct from `listen_delight_audit` (see below), which is the **authoritative** hard delight ship gate — G-Listen is an earlier, optional pass. |
| **Timeline optimizer** | Auto-starts after `mix` (defaults) | **Endless daemon (mode C)** permutes structure + glue + SDP + optional LLM proposals per run. GUI: Take best + remaster / Keep optimizing / Stop / Skip. Artifacts under `master/optimizer/`. Config: `mastering.timeline_optimizer`. |
| **`listen_delight_audit`** (not operator-facing) | After `assembly_preview`, before SFX craft | **Pre-mix score pass** (default non-blocking). Writes `mastering/listen_delight_audit.json`. **Authoritative ship block** re-runs at `master_finalize` after `master.wav` exists. Set `fail_early_at_audit_stage: true` to hard-stop pre-mix. See [narrative-mode-and-montage.md#listen-delight](../cross-cutting/narrative-mode-and-montage.md#listen-delight). |
| **G-Publish** | After `master_transcript_build` (Ship) | Optional local episode package + separate S3 sync for **this run only**. **Prepare package for this run:** `POST …/g-publish/continue` runs `master_transcript_build` (idempotent) then `episode_meta_build`…`podcast_publish` locally (no S3). **Upload this run to S3:** `POST …/g-publish/sync` (or `python scripts/sync_podcast_episodes.py --execution-id …`) uploads that run's complete `publish/` package including `transcript.vtt` — never sibling executions, skips if already on S3, never deletes S3. **Skip:** `POST …/g-publish/skip`. GUI shows the live feed URL plus the Apple Podcasts Connect pass-through (`new-feed?submitfeed=`). Apple rejects an empty seed feed. See [podcast-rss-hosting.md](../cross-cutting/podcast-rss-hosting.md). Note: reaching `master_finalize` already implies `listen_delight_audit` passed (authoritative mode) — Ship is not blocked again here for delight, only for the optional package/sync step. **PMQ before ship:** `master/post_master_quality.json` with `publish_allowed: true` is required before encode/package/S3; missing PMQ or failed checks mean the run is not ship-ready even when `master.wav` exists. Pre-mix publishability checkpoints (`post_edl`, `pre_mix`) catch producer contract drift earlier — see [publishability-contract.md](../cross-cutting/publishability-contract.md). |

## Informational gates (quality, not operator UI)

| Gate | When | Behavior |
|------|------|----------|
| **G-AirOrder** | Ranking / transitions / selection mutations | [`air-order-boundary.md`](../cross-cutting/air-order-boundary.md) — constitution checkpoints on `master/selection.json`; critical integrity in `master/air_order_integrity.json`. Default **warn-only** (`block_ranking_on_critical: false`); enable blocking after soak. PMQ backstop when `block_publish_on_critical: true`. When EDL or ranking loops on integrity, inspect `resolved_policy` in `master/air_order_integrity.json` (duration-scaled caps and family-based opening counts). |

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
