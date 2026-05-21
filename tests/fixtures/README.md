# Test fixtures

Run tests from an activated **Python 3.12** `.venv` (`source .venv/bin/activate`; see [SETUP.md](../../SETUP.md)).

## Speech sample (required for meaningful STT smoke tests)

Pipeline smoke tests need **real speech**, not a sine tone.

### Option A — macOS `say` (automatic in pytest on Darwin)

If you run `pytest` on a Mac with `say` and `ffmpeg`, tests generate a short clip automatically.

### Option B — Add a WAV file here

Place a 30s–5min interview or podcast clip at:

```text
tests/fixtures/speech_short.wav
```

Mono or stereo, any common format. Prefer clear single-speaker speech.

### Option C — Download script

```bash
./tests/fixtures/fetch_sample.sh
```

## What not to use

- `test_tone_30s.wav` / sine generators — only prove ffmpeg wiring, not podcast quality
- Silence-only files — STT may return empty segments

## Production (Step 6+)

Use your full interview recording via `INPUT_AUDIO_PATH` in `config/secrets/secrets.env` ([SETUP.md](../../SETUP.md) Step 6+).
