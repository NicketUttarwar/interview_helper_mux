# Capture

No pinned runtime beyond operator recording setup. Downstream stages use [anchored-toolchain.md](../../cross-cutting/anchored-toolchain.md) (`ffmpeg`, OpenAI, local MMAudio; optional Terraform + boto3 for RSS).

Operator provides raw interview audio before any automated stage.

## Input

- One or more `.wav` files anywhere under `ASSETS/` (recommended folder: `ASSETS/input/`; any filename)
- **GUI:** pick a file from the home **Input audio** list after `./scripts/run.sh` — no path in config required ([assets-and-executions.md](../../cross-cutting/assets-and-executions.md))
- Phone or Zoom recordings acceptable; avoid clipped peaks

## Output

- None (capture is manual)

## Assumptions

- Single continuous take preferred
- Stereo or mono; ingest normalizes to project standard

## Quality offer (optional)

If the recording has noticeable background noise, the app should **offer** [audio pre-clean](../audio_preclean/README.md) before ingest. The operator can also skip now and accept the same offer later (after transcript review, after pickup VO at G1, or before final mix).

Default path: straight to [ingest](../ingest/README.md) with no API call.

## Next stage (default)

[ingest](../ingest/README.md)
