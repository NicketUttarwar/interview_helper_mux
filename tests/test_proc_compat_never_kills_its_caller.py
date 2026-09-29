"""A process sweep must never kill the shell that launched it.

Found by running a cleanup helper that takes its pattern as an argument:

    python tools/cleanup_stale_processes.py --pattern interview_mux.stage_worker

The pattern is then part of the invoking shell's own command line, so a sweep
that matches command lines matches that shell. ``_filter_pids`` excluded only
``os.getpid()``, so the parent was a legitimate target, and on Windows
``taskkill /T`` takes the whole tree. The observed symptom was the tool
producing no output at all and the shell dying, which reads like a crash rather
than a sweep working exactly as written.

``pgrep -f`` has the same exposure on POSIX. The shell code this replaced avoided
it only because its patterns were literals in the script, never arguments.
"""

from __future__ import annotations

import os

import pytest

from interview_mux import proc_compat


def test_direct_parent_is_never_a_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proc_compat, "IS_WINDOWS", False)
    monkeypatch.setattr(
        proc_compat,
        "_iter_pid_cmdlines",
        lambda: [(os.getppid(), "bash run.sh --pattern needle"), (999123, "python needle")],
    )
    monkeypatch.setattr(
        proc_compat.subprocess, "check_output", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    pids = proc_compat.pids_matching("needle")
    assert os.getppid() not in pids, "the invoking shell must not be a kill target"
    assert 999123 in pids, "unrelated matches must still be found"


def test_whole_ancestor_chain_is_protected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Not just the parent: a grandparent shell is equally fatal to kill."""
    me = os.getpid()
    monkeypatch.setattr(
        proc_compat, "_pid_ppid_map", lambda: {me: 500, 500: 400, 400: 300, 300: 1}
    )
    chain = proc_compat._self_and_ancestors()
    assert {me, 500, 400, 300} <= chain
    assert 1 not in chain, "init is filtered out, not protected as an ancestor"


def test_ancestor_walk_survives_a_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bogus ppid table must not spin forever."""
    me = os.getpid()
    monkeypatch.setattr(proc_compat, "_pid_ppid_map", lambda: {me: 700, 700: 800, 800: 700})
    chain = proc_compat._self_and_ancestors()  # must terminate, not hang
    assert {me, 700, 800} <= chain
    assert len(chain) <= 5, "a cycle must not inflate the protected set"


def test_self_and_parent_protected_even_with_no_process_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Degrade safely: an unavailable ppid map must not drop the protection."""
    monkeypatch.setattr(proc_compat, "_pid_ppid_map", lambda: {})
    chain = proc_compat._self_and_ancestors()
    assert os.getpid() in chain
    assert os.getppid() in chain or os.getppid() <= 1


def test_exclude_self_false_still_returns_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unfiltered list stays reachable for a caller that really means it."""
    monkeypatch.setattr(proc_compat, "IS_WINDOWS", False)
    monkeypatch.setattr(
        proc_compat,
        "_iter_pid_cmdlines",
        lambda: [(os.getppid(), "bash needle")],
    )
    monkeypatch.setattr(
        proc_compat.subprocess, "check_output", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    assert proc_compat.pids_matching("needle", exclude_self=False) == [os.getppid()]


def test_posix_pgrep_results_are_also_filtered(monkeypatch: pytest.MonkeyPatch) -> None:
    """pgrep -f matches the invoking shell too, so its output needs the same guard."""
    monkeypatch.setattr(proc_compat, "IS_WINDOWS", False)
    parent = os.getppid()

    def fake_check_output(cmd, **kwargs):
        return str(parent) + chr(10) + "999124" + chr(10)

    monkeypatch.setattr(proc_compat.subprocess, "check_output", fake_check_output)
    pids = proc_compat.pids_matching("needle")
    assert parent not in pids
    assert pids == [999124]
