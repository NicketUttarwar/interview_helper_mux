# Operator gates — v2 simplified

**0.0.0:** these gates behave as today. **0.1.0 (default):** the homunculus is the gate controller (categories); G0 word-level still requires a human when open. See [mastering-homunculus.md](../cross-cutting/mastering-homunculus.md).

**Why these gates exist:** G0 protects **idea transmission** — a wrong word or mis-attributed clause at the source poisons every downstream stage (analysis, gap detection, VO, EDL) that trusts the transcript. **Tier-0 publishability** still hard-stops contract breaks. **Quality rubrics** are aspiration signals by default (`mastering.aspirational_quality.enabled`): up to three remutate/heal attempts per family, then pick-best master + `quality_advisories`. `master_finalize` produces `master.wav` when structurally sound; S3/RSS needs G-Publish when advisories are present. See [NORTH_STAR.md#human-listen-rubric-ship-checklist](../../NORTH_STAR.md#human-listen-rubric-ship-checklist).

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
| **G1** | `g1_vo_pickup` | **Optional.** Reachable after nugget layups publish `gap_report` and/or `gap_framing_recompose` accepts/skip-copies — [flow integrity](../cross-cutting/refinement-passes.md) guarantees `understanding/gap_report.json` is authoritative. Expect **more/longer before-VO lay-ups** recovering excluded-tape facts ([nugget-layup-system.md](../cross-cutting/nugget-layup-system.md)). Record or synthesize gap lines, or **Skip — continue without gap VO** (`POST …/g1/skip-optional`). Batch synthesize: `POST …/g1/synthesize-all`. **GUI:** `GET /api/runs/{id}` exposes `operator_gates.g1_vo_pickup` — when `operator_must_act` is false (optional or `automation_pending` under partial-auto + Chatterbox), the journey does not block and the NEEDS YOU banner is suppressed. `g1_clear` follows journey semantics (not raw WAV presence). |

**Partially accelerated G0 timing:** prepare-until-G0 runs `ingest → transcribe → transcript_review_build` only (defers `audio_preclean` until after operator review). Full-auto and manual runs keep preclean-before-ingest.

## Non-gates (optional offers)

| Offer | When | Behavior |
|-------|------|----------|
| Pre-clean source | Before ingest | Never auto-run; dismissible |
| NLE edits | After ranking / before EDL | Operator choice via Timeline tab |
| Assembly preview listen | After `assembly_preview` | Soft milestone; does not block mix by default |
| **G-Listen** | After `mix` when `master/listen_critic.json` recommends (`g_listen_recommended`) | Optional borderline quality review before `master_finalize`. Default `sound_design.g_listen_mode: warn` (advisory). Set `block` to hard-stop. Continue: `POST …/g-listen/continue`; skip: `POST …/g-listen/skip`. Distinct from `listen_delight_audit`, which scores the human-listen rubric (aspiration floors by default). |
| **Timeline optimizer** | Auto-starts after `mix` (defaults) | **Endless daemon (mode C)** permutes structure + glue + SDP + optional LLM proposals per run. GUI: Take best + remaster / Keep optimizing / Stop / Skip. Artifacts under `master/optimizer/`. Config: `mastering.timeline_optimizer`. |
| **`listen_delight_audit`** (not operator-facing) | After `assembly_preview`, before SFX craft | **Pre-mix score pass** (default non-blocking). Writes `mastering/listen_delight_audit.json`. Re-evaluates at `master_finalize`. Floors are advisory unless `aspirational_quality.enabled: false` and `listen_delight.mode: authoritative`. Activity banner when `aspirational_proceeded`. **Full-auto Phase B/C:** after an audit artifact exists, `operator/escalations/listen_delight_audit.json` with `status: waived_unattended` lets music proceed (logged on `operator/delivery_checkpoint.json`). |
| **G-Publish** | After `master_transcript_build` (Ship) | Optional local episode package + separate S3 sync for **this run only**. … Note: `master_finalize` produces `master.wav` when Tier-0 passes; advisories do not block local encode. **S3 sync** requires operator consent when `quality_advisories` is non-empty. **PMQ:** `publish_allowed: true` on master completion; `advisory_fail` rubric-only status is normal under aspirational policy. Pre-mix publishability checkpoints catch producer contract drift earlier — see [publishability-contract.md](../cross-cutting/publishability-contract.md). |
| **G-DeliveryUnlock** | After Phase A seal (`delivery_epoch.locked`) | Structural reruns that would archive assembly/mix/music (e.g. second `nugget_layup_compose` with order drift) are blocked until the operator unlocks the delivery epoch: `POST /api/runs/{id}/delivery/unlock` with a reason. Heal-only invalidations (matching checkpoint fingerprints) proceed without unlock. |

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
