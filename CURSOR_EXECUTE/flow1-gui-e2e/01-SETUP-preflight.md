# Step 01 — SETUP preflight

**Purpose:** Verify toolchain, secrets, input asset, GUI bundle, Playwright, and dummy VO fixture before browser automation.

---

## Checks (run.sh prints each as INFO pass/fail)

```bash
# From repo root
test -f ASSETS/notebooklm_original_interview_2024.wav
test -f config/secrets/secrets.env
./tools/check_prerequisites.sh
./CURSOR_EXECUTE/bootstrap_venv.sh
source CURSOR_EXECUTE/.venv/bin/activate
pip install -q -e "CURSOR_EXECUTE/.[e2e]"
playwright install chromium
./fixtures/generate_dummy_vo.sh
```

| Check | Requirement |
|-------|-------------|
| Input WAV | `ASSETS/notebooklm_original_interview_2024.wav` exists |
| Secrets | `config/secrets/secrets.env` with API keys |
| Toolchain | `check_prerequisites.sh` — ffmpeg, Python 3.12 |
| GUI static | `interview_mux.gui_bundle.needs_gui_build()` false or build |
| Playwright | `CURSOR_EXECUTE/.venv` + chromium browser |
| Dummy VO | `fixtures/dummy_vo.wav` (3s tone for G1 upload) |

---

## Optional local stacks (warn if missing)

- `ASSETS/local_mmaudio/venv` — MMAudio SFX stages
- `ASSETS/local_deepfilter/venv` — optional preclean

See [docs/cross-cutting/local-audio-stack.md](../../docs/cross-cutting/local-audio-stack.md).

---

## Definition of done

- [ ] All checks above pass or documented waivers in a blocker ticket
- [ ] `00-INDEX.md` step **01** marked `[x]`
