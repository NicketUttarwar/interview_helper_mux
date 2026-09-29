"""Guards that the Windows port did not change behaviour on macOS or Linux.

The Windows work touched shared code: process management, venv layout, the
config overlay, and the bootstrap scripts. These tests pin the POSIX side of
each decision so a future change cannot quietly regress the Mac, which is the
machine this project is actually developed on.

They run on every platform: the POSIX-only assertions are driven by patching
``proc_compat.IS_WINDOWS`` rather than by skipping.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from interview_mux import proc_compat

REPO = Path(__file__).resolve().parents[1]
CRLF = b"\r\n"


# --- process management: POSIX must keep using pgrep / lsof ------------------


def test_posix_pids_matching_uses_pgrep_even_when_psutil_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """psutil on a Mac must not silently change matching semantics."""
    monkeypatch.setattr(proc_compat, "IS_WINDOWS", False)
    monkeypatch.setattr(proc_compat, "_psutil", lambda: object())  # pretend installed

    calls: list[list[str]] = []

    def fake_check_output(cmd, **kwargs):
        calls.append(list(cmd))
        return "4242\n"

    monkeypatch.setattr(proc_compat.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(
        proc_compat,
        "_iter_pid_cmdlines",
        lambda: pytest.fail("POSIX must use pgrep, not the generic scan"),
    )

    assert proc_compat.pids_matching("some_driver.py") == [4242]
    assert calls and calls[0][0] == "pgrep"
    assert calls[0][1] == "-f"


def test_posix_pgrep_no_match_returns_empty_not_a_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pgrep exiting 1 means 'no match', which must not fall through to psutil."""
    monkeypatch.setattr(proc_compat, "IS_WINDOWS", False)

    def fake_check_output(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(proc_compat.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(
        proc_compat,
        "_iter_pid_cmdlines",
        lambda: pytest.fail("a clean pgrep miss must not trigger the generic scan"),
    )
    assert proc_compat.pids_matching("nothing_here") == []


def test_posix_falls_back_only_when_pgrep_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host without pgrep still works, via the generic scan."""
    monkeypatch.setattr(proc_compat, "IS_WINDOWS", False)

    def fake_check_output(cmd, **kwargs):
        raise FileNotFoundError("pgrep missing")

    monkeypatch.setattr(proc_compat.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(
        proc_compat, "_iter_pid_cmdlines", lambda: [(99, "x some_driver.py")]
    )
    assert proc_compat.pids_matching("some_driver.py") == [99]


def test_posix_port_probe_uses_lsof(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proc_compat, "IS_WINDOWS", False)
    calls: list[list[str]] = []

    def fake_check_output(cmd, **kwargs):
        calls.append(list(cmd))
        return "777\n"

    monkeypatch.setattr(proc_compat.subprocess, "check_output", fake_check_output)
    assert proc_compat.pids_listening_on_port(8765) == [777]
    assert calls and calls[0][0] == "lsof"


def test_posix_detach_uses_start_new_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """The original POSIX detach semantics must be preserved exactly."""
    monkeypatch.setattr(proc_compat, "IS_WINDOWS", False)
    kwargs = proc_compat.detach_kwargs()
    assert kwargs == {"start_new_session": True}
    assert "creationflags" not in kwargs


def test_windows_detach_does_not_use_start_new_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """start_new_session is POSIX-only and silently ignored on Windows."""
    monkeypatch.setattr(proc_compat, "IS_WINDOWS", True)
    kwargs = proc_compat.detach_kwargs()
    assert "start_new_session" not in kwargs
    assert int(kwargs.get("creationflags") or 0) != 0


def test_never_signals_pid_0_or_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bad probe result must never be able to signal init or the whole group."""
    monkeypatch.setattr(proc_compat, "IS_WINDOWS", False)
    sent: list[int] = []
    monkeypatch.setattr(proc_compat.os, "kill", lambda pid, sig: sent.append(pid))
    proc_compat.terminate_pids([0, 1, -1])
    assert sent == []


# --- bootstrap scripts ------------------------------------------------------


def test_deepfilter_clone_is_on_by_default() -> None:
    """macOS installs DeepFilterNet from this clone via maturin.

    bootstrap_local_runtimes.sh only builds when $DF_DIR/pyDF exists, so a clone
    that defaults to off silently removes preclean on the Mac.
    """
    text = (REPO / "scripts" / "clone_local_audio_repos.sh").read_text(encoding="utf-8")
    assert 'SKIP_DEEPFILTER_CLONE:-0}" != "1"' in text, "clone must default to ON"
    assert "CLONE_DEEPFILTER" not in text, "opt-in flag would skip the clone by default"


def _shell_scripts() -> list[str]:
    return [
        p.relative_to(REPO).as_posix()
        for p in sorted(REPO.glob("scripts/**/*.sh")) + sorted(REPO.glob("tools/**/*.sh"))
    ]


def test_committed_shell_scripts_have_no_crlf() -> None:
    """CRLF in a committed .sh breaks the shebang on macOS: 'bad interpreter: ^M'.

    Asserts on the committed bytes rather than the working tree: a Windows
    checkout may legitimately hold CRLF locally because .gitattributes
    normalises ``*.sh`` to LF on commit. What reaches the Mac is the blob.
    """
    rel = _shell_scripts()
    if not rel:
        pytest.skip("no shell scripts found")
    offenders = []
    for r in rel:
        blob = subprocess.run(
            ["git", "show", f"HEAD:{r}"], cwd=str(REPO), capture_output=True
        )
        if blob.returncode != 0:
            continue  # not committed yet
        if CRLF in blob.stdout:
            offenders.append(r)
    assert offenders == [], f"committed with CRLF, will break on POSIX: {offenders}"


def test_gitattributes_pins_shell_scripts_to_lf() -> None:
    """The guard above only holds because .gitattributes normalises on commit."""
    text = (REPO / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in text


def test_committed_python_has_no_crlf() -> None:
    """A CRLF-flipped .py is a whole-file diff that buries the real change.

    Python itself does not care, which is why this goes unnoticed: the file
    runs fine and the damage is only visible in review. On Windows, pathlib
    write_text translates newlines on the way out, so an edit made through it
    flips an LF file wholesale. 33 files were flipped that way before this was
    caught, each appearing as roughly 100% rewritten and hiding a 20-line fix
    inside a 2800-line diff.

    Asserts on the committed blob, not the working tree, because
    .gitattributes normalises on commit and a Windows checkout may legitimately
    hold CRLF locally. What reaches the Mac, and what a reviewer sees, is the
    blob.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "*.py"],
        cwd=str(REPO),
        capture_output=True,
        check=False,
    )
    if tracked.returncode != 0:
        pytest.skip("not a git checkout")
    names = [n for n in tracked.stdout.decode("utf-8").split(chr(0)) if n]
    assert names, "no tracked Python files found"
    offenders = []
    for rel in names:
        blob = subprocess.run(
            ["git", "show", f"HEAD:{rel}"], cwd=str(REPO), capture_output=True
        )
        if blob.returncode == 0 and CRLF in blob.stdout:
            offenders.append(rel)
    assert offenders == [], (
        "committed with CRLF, so every future edit shows as a whole-file diff: "
        f"{offenders[:10]}"
    )


def test_gitattributes_pins_python_to_lf() -> None:
    """The guard above only holds because the extension is pinned."""
    text = (REPO / ".gitattributes").read_text(encoding="utf-8")
    assert "*.py text eol=lf" in text


def test_run_sh_port_and_orphan_cleanup_is_not_posix_only() -> None:
    """run.sh must not gate its port/orphan sweeps on lsof or ps -ax.

    Those were wrapped in `command -v`, so on Windows the port sweep never ran
    and a stale server on 8765 had to be killed by hand before each launch. The
    `ps` sweep was worse: Git Bash provides a `ps`, so the guard passed, but it
    does not report native Windows command lines, so the greps matched nothing
    while appearing to work.
    """
    text = (REPO / "scripts" / "run.sh").read_text(encoding="utf-8")
    assert "tools/cleanup_stale_processes.py" in text
    # Match the invocation, not the comment that explains why it is gone.
    assert "$(lsof" not in text, "port sweep must not depend on lsof"
    assert "$(ps -ax" not in text, "orphan sweep must not depend on ps -ax"


def test_cleanup_helper_routes_through_proc_compat() -> None:
    """The helper must not reimplement process handling with its own shell calls."""
    text = (REPO / "tools" / "cleanup_stale_processes.py").read_text(encoding="utf-8")
    for name in ("pids_listening_on_port", "pids_matching", "terminate_pids"):
        assert name in text, f"helper should use proc_compat.{name}"
    for shelled in ("lsof", "taskkill", "netstat", "pgrep"):
        assert f'"{shelled}"' not in text, f"{shelled} belongs in proc_compat, not here"


def test_venv_layout_matches_platform() -> None:
    """bin/ on POSIX, Scripts/ on Windows, with the plain `python` name on POSIX.

    Asserted against the running platform rather than by faking os.name, since
    pathlib refuses to construct a PosixPath on Windows.
    """
    import os

    from interview_mux.venv_paths import BIN_DIR, venv_python

    expected_dir = "Scripts" if os.name == "nt" else "bin"
    expected_exe = "python.exe" if os.name == "nt" else "python"
    assert BIN_DIR == expected_dir
    py = venv_python(Path("nonexistent_venv_root"))
    assert py.parent.name == expected_dir
    assert py.name == expected_exe


def test_venv_layout_keys_off_os_name() -> None:
    """The layout choice must key off os.name, not a hardcoded platform."""
    from interview_mux import venv_paths

    src = Path(venv_paths.__file__).read_text(encoding="utf-8")
    assert 'os.name == "nt"' in src
    assert '"Scripts"' in src and '"bin"' in src


# --- config overlay ---------------------------------------------------------


def test_no_overlay_means_defaults_are_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """A machine without app.local.json (a macOS checkout) sees the shipped config."""
    from interview_mux import config as cfg_mod

    monkeypatch.setattr(cfg_mod, "shipped_defaults", lambda: {"a": 1, "b": {"c": 2}})
    monkeypatch.setattr(
        cfg_mod, "repo_root", lambda: Path("/nonexistent-root-for-overlay-test")
    )
    assert cfg_mod.load_defaults() == {"a": 1, "b": {"c": 2}}


def test_committed_defaults_carry_no_machine_paths() -> None:
    """app.defaults.json is shared; absolute host paths in it would break the Mac."""
    import json

    raw = (REPO / "config" / "app.defaults.json").read_text(encoding="utf-8")
    doc = json.dumps(json.loads(raw))
    for needle in ("C:/", "/Users/", "mux-local"):
        assert needle not in doc, f"machine path {needle!r} leaked into shared config"


def test_overlay_file_is_gitignored() -> None:
    """A committed app.local.json would push one machine's paths onto everyone."""
    proc = subprocess.run(
        ["git", "check-ignore", "-q", "config/app.local.json"],
        cwd=str(REPO),
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, "config/app.local.json must stay gitignored"


# --- oversized-request detection --------------------------------------------


def test_oversized_request_429_triggers_safe_pruning() -> None:
    """A 429 "Request too large" is an oversized request, not a burst.

    The provider states the input or output tokens must be reduced, which is
    exactly what safe pruning does. Before this, boundary_topic_resplit
    hard-failed on a real run 233 tokens over a 30k TPM cap because the detector
    only matched context_length wording.
    """
    from interview_mux.safe_pruning import is_context_length_error

    msg = (
        "Error code: 429 - {'error': {'message': 'Request too large for gpt-4o "
        "in organization org-x on tokens per min (TPM): Limit 30000, Requested "
        "30233. The input or output tokens must be reduced in order to run "
        "successfully.'}}"
    )
    assert is_context_length_error(Exception(msg))


def test_burst_rate_limit_does_not_trigger_safe_pruning() -> None:
    """Requests-per-minute throttling needs backoff, not a smaller prompt."""
    from interview_mux.safe_pruning import is_context_length_error

    msg = "Error code: 429 - Rate limit reached for requests per minute. Retry shortly."
    assert not is_context_length_error(Exception(msg))


def test_classic_context_length_still_detected() -> None:
    from interview_mux.safe_pruning import is_context_length_error

    assert is_context_length_error(Exception("This model maximum context length is 8192 tokens"))
    assert not is_context_length_error(Exception("Connection reset by peer"))
