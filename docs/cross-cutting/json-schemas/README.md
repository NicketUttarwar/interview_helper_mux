# JSON Schemas — index

**Validator:** `jsonschema` package pin — [anchored-toolchain.md](../anchored-toolchain.md). Use **Context7** when editing `prompt_validation.py`.

Schemas in this folder define **machine-checkable contracts** for interview mux runs.

## Layout

| Location | Contents |
|----------|----------|
| `*.schema.json` (this directory) | Shared objects: envelope, analysis state, segment, transcript review queue, investigation queue, `gap_report`, sound design plan, `run_meta`, `ingest_checksums`, `transcript_corrections`, `value_features`, **`llm_call_record`** |
| `artifacts/*.schema.json` | LLM stage **artifacts** validated by `interview_mux.prompt_validation` |

## Coverage and gaps

Not every file under [artifact-layout.md](../artifact-layout.md) has a schema yet. See **[json-schema-coverage.md](../json-schema-coverage.md)** for:

- Which stages are validated automatically
- Which artifacts still need schemas and suggested tickets
- **Guards** (registration in `STAGE_ARTIFACT_SCHEMAS`, CI, pre-mux checks)

## GUI validation (Zod)

Python **jsonschema** validates every pipeline and API write. The React GUI uses **Zod** schemas generated from these files:

```bash
python tools/codegen_zod_schemas.py
```

See [artifact-generation-and-validation.md](../artifact-generation-and-validation.md).

## Conventions

- Prefer **Draft 2020-12** (`$schema` URL in each file).
- Add **`schema_version`** (integer) at the root of evolving run artifacts when consumers must branch.
- Keep **prompt examples** and **schema enums** in sync — see [segment-schema.md](../segment-schema.md).
- After changing a schema wired to `ARTIFACT_WRITE_VALIDATORS`, run codegen + update [json-schema-coverage.md](../json-schema-coverage.md).
