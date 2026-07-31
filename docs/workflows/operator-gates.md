# Operator gates — v2 simplified

Canonical charter: [NORTH_STAR.md](../../NORTH_STAR.md).

## Hard gates

| Gate | ID | Behavior |
|------|-----|----------|
| **G0** | `transcript_review` | **Mandatory.** Pipeline stops after `transcript_review_build` until STT corrections are complete. |
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
| **G-Listen** | After `mix` when `master/listen_critic.json` recommends (`g_listen_recommended`) | Optional borderline quality review before `master_finalize`. Default `sound_design.g_listen_mode: warn` (advisory). Set `block` to hard-stop. Continue: `POST …/g-listen/continue`; skip: `POST …/g-listen/skip`. |
| **Timeline optimizer** | Auto-starts after `mix` (defaults) | **Endless daemon (mode C)** permutes structure + glue + SDP + optional LLM proposals per run. GUI: Take best + remaster / Keep optimizing / Stop / Skip. Artifacts under `master/optimizer/`. Config: `mastering.timeline_optimizer`. |

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
