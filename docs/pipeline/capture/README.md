# Capture

Operator provides raw interview audio before any automated stage.

## Input

- File under `ASSETS/input/` (default `interview.wav`)
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
