# Test isolation — what keeps the suite off the operator's real tree

`pytest tests/` runs against a checkout that also holds the operator's media (`ASSETS/input/`,
~630 MB of source audio) and 35 genuine executions (`ASSETS/executions/`, one of them a 5.9 G
forensic artifact). A test that resolves a live path does not fail — it succeeds slowly and
destructively. This doc is the inventory of what stops that, and the one trap that looks like it
does and does not.

---

## Env vars: three that do nothing

| Name | Honored? |
|---|---|
| `INTERVIEW_MUX_ROOT` | **Yes** — [`config.repo_root()`](../../src/interview_mux/config.py) reads it before falling back to a cwd/`__file__` walk. Setting it relocates everything derived from the repo root. |
| `INTERVIEW_MUX_DATA_ROOT` | **No.** |
| `MUX_DATA_ROOT` | **No.** |
| `MUX_EXECUTIONS_ROOT` | **No.** |

The last three are honored **nowhere in `src/`**. Verify at any time:

```bash
rg -n 'INTERVIEW_MUX_DATA_ROOT|MUX_DATA_ROOT|MUX_EXECUTIONS_ROOT' src/   # expect: no matches
```

99 test files under `tests/` set at least one of them, and those tests were writing straight into
the live tree while appearing to be sandboxed — a name that reads like a safety mechanism and
silently is not. They are inert, not harmful: the autouse fixtures below cover those tests now, so
the existing uses are noise rather than a live hazard, and removing ~99 files' worth of dead
`monkeypatch.setenv` is churn best folded into whatever else touches each file.

**Do not implement support for them.** Two spellings of the same idea plus a third that duplicates
`executions_root` is worse than one honored variable. A test that needs its own root sets
`INTERVIEW_MUX_ROOT`, or uses the redirect fixture, which is the default.

---

## The autouse redirect (default: nothing reaches the real tree)

`RunContext.__init__` mkdirs the executions root *and* the run dir, so merely constructing one in
a test minted a directory in `ASSETS/executions` — a full suite once left 11,557 behind.

[`tests/conftest.py`](../../tests/conftest.py) redirects `assets_root`, `executions_root` and
`run_context.repo_root` at a per-test tmp sandbox. It **redirects rather than cleans up**, so
nothing is written to the real path even under `-x`, xdist, or a hard crash. A session-scoped
backstop keeps job threads that outlive their test off the live tree too, since the function-scoped
`monkeypatch` has unwound by the time they run.

Opt out with `@pytest.mark.real_executions_root` when a test supplies its own root.

---

## The subprocess guard (what a fixture cannot reach)

A **child process inherits no in-process patch.** It re-resolves the repo root from its own cwd and
`__file__`, reads the real `config/app.defaults.json`, and runs the real stage.

`audio_preclean` is the only member of `SUBPROCESS_STAGES`, so a single `POST /execute` test forked
`python -m interview_mux.stage_worker` and ran **DeepFilterNet over the operator's source audio**,
writing 1.5 G of chunk WAVs into a stray `ASSETS/executions/exec_guard_start_*`. The fork outlives
pytest: the daemon job thread dies at exit, the child does not.

The session-scoped `block_pipeline_subprocess` fixture refuses any `subprocess.Popen` whose argv
contains `-m interview_mux…`, records it against the active test, and fails that test at teardown
(the `RuntimeError` alone lands on a job thread, where nothing would see it). It is deliberately
narrow: ffmpeg, the MLX venvs and every other spawn are untouched, and no test has a legitimate
reason to run the pipeline as a module.

Opt out with `@pytest.mark.allow_pipeline_subprocess`.

**Testing the guard/acceptance behaviour without the fork:** patch
`JobRunner._stage_worker_cmd` to a harmless argv rather than stubbing `_run_subprocess_stage`, so
pid tracking and exit-code handling still run — then wait for `runner.lock_held(run_id)` to clear
before the test returns, because `monkeypatch` unwinds at teardown and an unwound argv patch is a
real fork on the next run. See
[`tests/test_execute_guard_regression.py`](../../tests/test_execute_guard_regression.py).

---

## Live media reads

There is no guard for *reading* `ASSETS/input/`, and adding one would be noisy: tests legitimately
read repo files, and attribution across job threads is unreliable. The failure mode is quieter than
a fork but not free — `RunContext.input_audio()` falls back to the configured source audio and
passes it through `ensure_wav_asset()`, which **transcodes the whole file with ffmpeg** when the
`.wav` sibling is missing or older than the source.

So: give a test its own `run_meta.json` with an `input_audio_path` pointing at a synthesized WAV
(`init_run_meta_for_test(ctx, input_audio_path=str(tone))`). Note that
`render_sfx_under_speech_preview` resolves `ctx.input_audio()` eagerly even when
`ingest/normalized.wav` wins the speech-source race, so supplying the local file is what keeps the
real podcast out of it.

---

## Other autouse guards

| Fixture | Effect | Opt out |
|---|---|---|
| `block_outbound_network` | Raises on `socket.connect` to anything but localhost | `@pytest.mark.allow_network`, `@pytest.mark.slow` |
| `fast_gpu_abort_backoff` / `fast_gpu_exclusive_cooldown` | Zeroes the real 30 s / 5 s waits between mocked runtimes | — |
| `clear_write_staging_context` | Stops `ContextVar` staging leaking across tests | — |
| `pytest_collection_modifyitems` | Skips `@pytest.mark.slow` (live MusicGen weights) | `--run-slow`, `MUX_RUN_SLOW_TESTS=1` |
