# Operator gates — v2 simplified

Canonical charter: [NORTH_STAR.md](../../NORTH_STAR.md).

## Hard gates

| Gate | ID | Behavior |
|------|-----|----------|
| **G0** | `transcript_review` | **Mandatory.** Pipeline stops after `transcript_review_build` until STT corrections are complete. |
| **G-Framing** | After `source_topology_build` | **Optional (default No).** Add interviewer framing audio (questions, summaries, prefaces, bridges)? `POST …/gap-framing/enable`. |
| **G-Speaker** | G-Framing = Yes | Confirm gap pickup speaker (`PickupSpeakerPanel`). |
| **G-VoiceRef** | G-Framing = Yes | Approve collated voice reference for Chatterbox (`VoiceReferencePanel`). |
| **G-Delivery** | G-Framing = Yes | Chatterbox clone (default) or record at G1 (`GapDeliveryPanel`). |
| **G1** | `g1_vo_pickup` | **Optional.** Record or synthesize gap lines, or **Skip — continue without gap VO** (`POST …/g1/skip-optional`). Batch synthesize: `POST …/g1/synthesize-all`. |

## Non-gates (optional offers)

| Offer | When | Behavior |
|-------|------|----------|
| Pre-clean source | Before ingest | Never auto-run; dismissible |
| NLE edits | After ranking / before EDL | Operator choice via Timeline tab |
| Assembly preview listen | After `assembly_preview` | Soft milestone; does not block mix by default |

## Removed gates (v2)

- G0.5 `disfluency_review`
- `analysis_profile` / `operator_verified`
- G2 flow selection
- G1.5 SFX prompt approval (default off: `g1_5_require_prompt_approval: false`)
- Per-stage write approval (auto-commit artifacts)
- Custom-run handoff acks

## LLM failures

v2 uses **schema validate → one retry → hard stop** (`llm_simple.py`). No LLM-arbiter / investigation-queue UI on the default path (that is an optional **LLM volley** review surface — not **speaker volley** conversation structure). Re-run with `--from-stage <id>` after fixing upstream artifacts. See [volley-glossary.md](../cross-cutting/volley-glossary.md).

See [docs/v2/drop-manifest.md](../v2/drop-manifest.md).
