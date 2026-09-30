# CLAUDE.md

Context for Claude Code sessions in this checkout. Repo-wide agent guidance
lives in [AGENTS.md](AGENTS.md); this file covers only what is specific to
**this machine and this working arrangement**.

## Why this checkout exists

This is a **debugging checkout**, not a production one. Swapnil runs the app
here to find bugs, then reports fixes back upstream to the repo owner.

- Log every bug and fix in **[ISSUES.md](ISSUES.md)** so it can be handed over.
- Fork: `swapnilgarg7/interview_helper_mux`. Remote `fork`; `origin` is upstream.
- Work on branches off the fork and open PRs against `swapnilgarg7:main`.
  **Do not open PRs against `origin` (upstream) without asking**: it
  notifies the upstream owner and is visible on their repo.

## This machine

Windows 11, NVIDIA GTX 1660 SUPER (6 GB VRAM, sm_75, no bf16), 16 GB RAM.
Upstream targets macOS Apple Silicon, so the MLX stacks are replaced with CUDA
equivalents behind the same contracts. Details and rationale:
**[docs/cross-cutting/windows-cuda-setup.md](docs/cross-cutting/windows-cuda-setup.md)**.

- **Run scripts from Git Bash**, not PowerShell. They are bash.
- **Heavy stacks live at `C:\mux-local`**, not under `ASSETS/`. Windows caps
  paths at 260 chars and `pip install torch` fails outright inside this repo's
  OneDrive path. It also keeps ~35 GB of weights out of cloud sync.
- **`config/app.local.json` is gitignored and machine-specific.** It holds the
  `C:\mux-local` paths and the VRAM-sized MusicGen tier. Never commit it, and
  never move these values into `config/app.defaults.json`, which is shared and
  would break the M1. A fresh clone needs this file recreated.
- **`PYTHONUTF8=1` is required.** The pipeline logs non-ASCII and Windows
  defaults to cp1252, which makes subprocess stdout raise `UnicodeEncodeError`.
  `run.sh` exports it; set it yourself for direct `pytest` or CLI runs.
- **ffmpeg** is on the user PATH but new shells may need a restart to see it:
  `C:\Users\Swapnil\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-*\bin`
- Python 3.12 is the core interpreter. The DeepFilter venv is **3.11** on
  purpose: `DeepFilterLib` publishes no cp312 wheel.

## Commands

```bash
./scripts/run.sh                          # GUI at http://127.0.0.1:8765
./scripts/run.sh --cli run --run-id ...   # headless, one phase
python -m interview_mux orchestrate --mode full-auto --input <wav>   # the engine (ISSUES 79)
python -m interview_mux orchestrate --mode partially-accelerated --run-id exec_...
MUX_STAGE_CACHE=0 ...                     # force transcribe/probes to rerun (ISSUES 93)
MUX_REBUILD_GUI=1 ./scripts/run.sh        # rebuild React bundle first
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q          # full suite, ~17 min
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -n 12   # same suite, ~8 min

./scripts/bootstrap_venv_windows.sh                # setup (NOT bootstrap_venv.sh)
python scripts/download_local_models_cuda.py --verify
```

Runs land in `ASSETS/executions/exec_*`.

## Keyless pipeline traversal

```bash
python tools/stub_pipeline_smoke.py --audio <real_speech.wav> --keep
python tools/stub_pipeline_smoke.py --from boundary_detection --run-id exec_NNN_...
```

Walks all 72 stages with no API key: `MUX_STUB_LLM=1` answers every OpenAI call
from the schema the stage requested. Reports `ok` / `NOOP` / `FAIL` per stage,
where NOOP means the stage returned cleanly but wrote no artifact, which is the
difference between a real pass and a silent skip.

**Current reach with a real key: 72 of 72 on the full one-hour source**
(`exec_052`, 59.5-minute interview: master.wav 48.1 min, publish/audio.mp3,
cover, chapters, transcript.vtt; no 429s on the default routing), and on the
6-minute excerpt (`exec_046`, `exec_047`, `exec_049`, `exec_050`). `exec_055` is the
second one-hour run (51.3-minute master, entries 67 to 76 fixed along the way:
the removal authority, the ordering-gate sweep). exec_052 was
re-entered after each new defect (ISSUES.md entries 54 to 66, all fixed); a
from-scratch run that needs no re-entry is the standing check (entry 45).
Keyless stub: 41 stages.

Engine proofs (2026-09-30): `exec_062` full-auto through the GUI path, 72 of
72, 4.3-minute master from the 6-minute clip (entries 84, 85). `exec_063`
partially-accelerated through the GUI endpoints, 72 of 72 after entries 94
to 98 were fixed along the way (the engine was restarted three times on the
same run; each restart re-verified analysis in about 10 s). Stage cache
(entry 93) lives at `C:\mux-local\stage_cache` here.

Ordering exceptions ("may X run before Y is complete") live only in
`src/interview_mux/ordering_authority.py` (entry 62). Add new ones there; a
test fails if an ordering check grows its own copy.

Whether a segment may come off air is decided only in
`src/interview_mux/removal_authority.py` (entry 74), at the two write points
(air-order commit, NLE exclude). Local hard-keep guards are early exits, not
the decision.

Two diagnostics when a run stops somewhere new: `MUX_TRACE_WRITES=1` records
every manifest/boundaries write with stage and caller frames to
`<run_dir>/write_trace.log`; `MUX_STUB_TRACE=1` prints the stub's array
decisions. The driver hops back to analysis when delivery invalidates an
analysis stage, and retries a phase when the previous pass made progress.

Run the real model with `MUX_STUB_LLM=0` (the driver defaults the stub on).
Watch any run with `python tools/run_monitor.py --watch`.

The remaining stops are the **test audio**, not the pipeline. A single-speaker
lecture plus no diarization makes transcript_normalize._infer_turn_speakers
fabricate an alternating two-speaker conversation (see ISSUES.md entry 22), so the
gap-framing stages are asked to write interviewer lines for a speaker who is not
on the tape. To go further: a real two-person interview, and diarization
installed. Stage 14
`boundary_detection` is the ceiling and is *not* a bug: its gate computes
`reject` from coverage and segment duration, which schema-shaped output cannot
satisfy. Everything past it, including the whole 40-60 band, needs a real key.

Needs real speech audio: the synthetic tone fallback transcribes to nothing, so
stages past `speaker_roles` starve. `--from` re-enters at any stage, which avoids
redoing `audio_probe_build` (~299 s, the slowest stage).

## Scope

- **Terraform and podcast RSS publish are out of scope.** Do not set them up or
  debug them; they are the last stage and explicitly deferred.
- Local model stacks are installed and verified working, **including diarization** (Sortformer via NeMo in `C:/mux-local/local_diarize/venv`, ungated, no HF token). They are reported working upstream too. Suspect the **LLM-driven delivery band, stages 40 to 60** first.
  See [ISSUES.md](ISSUES.md).

## Test baseline

**6878 passed, 0 failed, 21 skipped** (2026-09-30, after ISSUES 85 to 93). Keep it there.

Launch pytest from Git Bash. From PowerShell, `bash` resolves to the WSL stub
in System32 and two tests that shell out to bash fail for that reason alone
(`test_r_wf_musicgen_stub_forbidden_via_verify`, and the gap-framing hollow
done test which then cannot resolve the Chatterbox venv).

**ffmpeg must be on PATH** or the suite aborts at once with a message naming it.
The pipeline shells out to a bare `ffmpeg` in 22 places, so this is a real
dependency, not a test detail. A shell opened before ffmpeg was installed holds a
stale PATH and will fail this check.

Run it with **`-n 12`** (pytest-xdist, 16 cores here): 17 min to 8 min, verified
to produce the identical count as the serial run. xdist is installed in the
venv but deliberately **not** added to `requirements.lock`, so a fresh clone and
a macOS checkout are unaffected; `pip install pytest-xdist` enables it.

It started at 6624 passed / 23 failed on this machine. All 23 are resolved: 6
real product defects, 8 stale tests or thin fixtures, 3 environment or hardware
limits now skipped with an explicit reason, and the rest duplicates of the same
root causes. Root cause and fix for each is in [ISSUES.md](ISSUES.md).

The 22 skips name why they cannot run here (no API key, no operator run data,
not Apple Silicon) instead of silently passing. A skip count above 22, or any
failure, means something regressed.

## Conventions

- No em dashes in generated text, anywhere (code comments, docs, commit
  messages, PR bodies).
- No AI attribution or `Co-Authored-By` trailers in commits.
- Never let unvalidated metadata drive an expensive operation. A declared
  duration, size, or count from a file header or API response gets a sanity
  check against a real measure before it becomes a loop bound, an allocation,
  or an ffmpeg `-t` argument. Give such subprocesses a timeout as a backstop.
