# 05 — BUILD-SS-04 verify + remux

`soundscape_verify.py`, report artifact, one remux, `tools/validate_soundscape.py`.

## Verify

```bash
pytest tests/ -k "soundscape_verify" -q
python tools/validate_soundscape.py --help
```
