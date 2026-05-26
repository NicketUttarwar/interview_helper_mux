# Segment schema — shapes, flags, alignment, and guards

Two related problems hurt fidelity if left implicit: **(1)** treating every JSON “segment” as the same shape when files differ by stage, and **(2)** prompts, docs, and JSON Schema drifting apart (e.g. `flags` named in prompts but missing from the canonical segment schema).

This page is the **single alignment reference** for segment data.

---

## Two segment shapes (do not conflate)

### 1. Timeline segment (full)

**Where:** `segments/manifest.json` after merge with boundaries (timestamps + text), gap fields, and any GUI edits — conceptually the **full** segment row the pipeline and mux reason about.

**Canonical schema:** [json-schemas/segment.schema.json](./json-schemas/segment.schema.json)

**Required fields (schema):** `segment_id`, `start_ms`, `end_ms`, `speaker_id`, `speaker_role`, `type`, `text`

**Common optional fields:** `topic_tags`, `ready`, `self_explanatory`, `flags`

### 2. Classification artifact slice (partial)

**Where:** LLM output for stage `segment_classification` — validated as [artifacts/manifest_artifact.schema.json](./json-schemas/artifacts/manifest_artifact.schema.json).

**Purpose:** Types, roles, tags, and **flags** per `segment_id` without re-sending full transcript text in the artifact (boundary detection already proposed ranges; the runtime merges slices into the full manifest).

**Required in artifact:** `segment_id`, `type`, `speaker_id`, `speaker_role`, `topic_tags`

**Optional:** `flags`

**Guard:** Code that **reads** `manifest.json` must tolerate either “full rows” or “merge artifact + boundaries” depending on pipeline version — prefer always writing **full** rows to disk after merge so downstream always sees [segment.schema.json](./json-schemas/segment.schema.json).

---

## `flags` vocabulary (prompt ↔ schema aligned)

Used in [segment-classification.system.txt](../prompts/segmentation/segment-classification.system.txt). Allowed values (same in `segment.schema.json` and `manifest_artifact.schema.json`):

| Flag | Meaning |
|------|--------|
| `starts_mid_thought` | Answer or block begins mid-idea; may need bridge or prior context |
| `references_prior_missing` | Refers to earlier content not available to a clip listener; often becomes `missing_callback` in gap analysis |
| `heavy_crosstalk` | Overlapping speech; STT / diarization may be unreliable |

**Rules:**

- Only use flags from this set — unknown flag strings should fail schema validation (intentional guard).
- Omit `flags` or use `[]` when none apply.

---

## Segment types and speaker roles

Enums match [segment.schema.json](./json-schemas/segment.schema.json) and the classification artifact:

**Types:** `interviewer_question`, `interviewee_answer`, `interviewer_reaction`, `setup`, `aside`, `coda`

**Roles:** `interviewer`, `interviewee`, `unknown`

---

## Speaker (roles file)

Separate from segment rows; see `understanding/speakers.json` and [artifacts/speakers_artifact.schema.json](./json-schemas/artifacts/speakers_artifact.schema.json).

```json
{
  "id": "spk_0",
  "role": "interviewer",
  "display_name": null,
  "confidence": 0.92,
  "evidence": "short turns, question density"
}
```

---

## Collections on disk

| File | Typical shape |
|------|----------------|
| `segments/boundaries.json` | Proposed splits — [boundaries_artifact.schema.json](./json-schemas/artifacts/boundaries_artifact.schema.json) |
| `segments/manifest.json` | `{ "segments": [ … ] }` — rows should satisfy **timeline** [segment.schema.json](./json-schemas/segment.schema.json) once merged |

---

## Best-in-class fixes (alignment)

1. **One enum source of truth:** Segment `type`, `speaker_role`, and `flags` values are defined in JSON Schema; prompts must use the same tokens (no synonyms).
2. **Validate at write time:** `segment_classification` artifacts are validated via `validate_stage_artifacts` — extended enums catch LLM drift early with retry feedback.
3. **When extending flags:** Add the token to **both** `segment.schema.json` and `manifest_artifact.schema.json`, then update this doc and [segment-classification.system.txt](../prompts/segmentation/segment-classification.system.txt) in the same change.

---

## Resilience guards (checklist)

| Guard | Action |
|-------|--------|
| Schema vs prompt | Changing a prompt’s allowed `type` / `flags` without updating schemas → CI or local validation fails on fixtures |
| Full manifest on disk | After merge, ensure `manifest.json` segments include `start_ms` / `end_ms` / `text` before gap or ranking stages |
| Downstream assumptions | Gap / ranking code must not read `flags` unless merge step copies them onto full segments |
| Coverage doc | See [json-schema-coverage.md](./json-schema-coverage.md) for which files are schema-backed vs TBD |

---

## Related

- [segment-classification.examples.md](../prompts/_shared/examples/segment-classification.examples.md) — classification good vs bad patterns
- [json-schema-coverage.md](./json-schema-coverage.md) — which artifacts have schemas
- [artifact-layout.md](./artifact-layout.md) — paths
- [logic-tree.md](../logic-tree.md) — segment semantics in decisions
