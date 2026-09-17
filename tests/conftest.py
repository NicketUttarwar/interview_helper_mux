"""Shared pytest fixtures — outbound network guard for offline unit tests."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any

import pytest

_ALLOWED_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_ORIGINAL_CONNECT = socket.socket.connect


def _guarded_connect(self, address) -> None:  # type: ignore[no-untyped-def]
    if isinstance(address, tuple) and len(address) >= 1:
        host = address[0]
        if isinstance(host, str) and not host.startswith("/") and host not in _ALLOWED_HOSTS:
            raise RuntimeError(
                f"Outbound network blocked in tests (connect to {host!r}). "
                "Use monkeypatch to stub external calls."
            )
    return _ORIGINAL_CONNECT(self, address)


@pytest.fixture(autouse=True)
def block_outbound_network(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Block external HTTP/TCP; allow localhost for FastAPI TestClient.

    Opt out with ``@pytest.mark.allow_network`` or ``@pytest.mark.slow`` (live MusicGen).
    """
    if request.node.get_closest_marker("allow_network") or request.node.get_closest_marker("slow"):
        return
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)


@pytest.fixture(autouse=True)
def fast_gpu_abort_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must not pay the real 30s abort backoff between mocked runtimes."""
    monkeypatch.setenv("INTERVIEW_MUX_GPU_ABORT_BACKOFF_SEC", "0")


@pytest.fixture(autouse=True)
def fast_gpu_exclusive_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must not pay the real 5s local_gpu settle between mocked runtimes."""
    monkeypatch.setenv("INTERVIEW_MUX_GPU_COOLDOWN_SEC", "0")


@pytest.fixture(scope="session", autouse=True)
def executions_root_backstop(tmp_path_factory: pytest.TempPathFactory):
    """Session-wide floor under the per-test redirect.

    Job threads started by a test can outlive it, and the function-scoped
    ``monkeypatch`` is undone by then — without this they mint run directories in
    the live tree after the test that spawned them has passed.
    """
    from interview_mux import run_context

    real_merged_config = run_context.merged_config
    real_repo_root = run_context.repo_root
    sandbox = tmp_path_factory.mktemp("mux_backstop_root")
    (sandbox / "ASSETS" / "executions").mkdir(parents=True)

    def _sandboxed_config() -> dict:
        cfg = dict(real_merged_config())
        cfg["assets_root"] = str(sandbox / "ASSETS")
        cfg["executions_root"] = str(sandbox / "ASSETS" / "executions")
        return cfg

    mp = pytest.MonkeyPatch()
    mp.setattr(run_context, "merged_config", _sandboxed_config)
    mp.setattr(run_context, "repo_root", lambda: sandbox)
    try:
        yield {"merged_config": real_merged_config, "repo_root": real_repo_root}
    finally:
        mp.undo()


@pytest.fixture(autouse=True)
def redirect_executions_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request: pytest.FixtureRequest,
    executions_root_backstop: dict,
) -> None:
    """Keep run directories out of the live ``ASSETS/executions``.

    ``RunContext.__init__`` mkdirs the executions root and the run dir, so any
    test that builds one without isolation mints a directory in the real tree.
    Redirecting the config (rather than cleaning up afterwards) means nothing is
    ever written there, which survives ``-x``, xdist, and hard crashes.

    ``repo_root`` moves with it, so ``ctx.root`` still contains ``ctx.run_dir``
    and repo-relative bookkeeping such as ``run_meta.storage_root`` resolves.

    Opt out with ``@pytest.mark.real_executions_root`` when a test supplies its
    own root (e.g. via ``INTERVIEW_MUX_ROOT``).
    """
    from interview_mux import run_context
    from run_fixtures import patch_executions_root

    if request.node.get_closest_marker("real_executions_root"):
        for attr, real in executions_root_backstop.items():
            monkeypatch.setattr(run_context, attr, real)
        return

    # A dedicated subdir, never tmp_path itself: many tests mkdir tmp_path/ASSETS
    # without exist_ok, and the sandbox has to stay out of their way.
    sandbox = tmp_path / "_mux_root"
    patch_executions_root(monkeypatch, sandbox)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: sandbox)


_ACTIVE_TEST: dict[str, Any] = {"nodeid": "<session>", "allow_pipeline_subprocess": False}
_PIPELINE_SPAWNS: list[str] = []


def _pipeline_module_spawn(args: Any) -> str | None:
    """Return the command line when ``args`` runs an ``interview_mux`` module."""
    if isinstance(args, (str, bytes, os.PathLike)):
        argv = os.fsdecode(args).split()
    else:
        try:
            argv = [os.fsdecode(a) if isinstance(a, (bytes, os.PathLike)) else str(a) for a in args]
        except TypeError:
            return None
    for flag, mod in zip(argv, argv[1:]):
        if flag == "-m" and (mod == "interview_mux" or mod.startswith("interview_mux.")):
            return " ".join(argv)
    return None


@pytest.fixture(scope="session", autouse=True)
def block_pipeline_subprocess():
    """Refuse to fork the pipeline out of a test.

    A child process inherits none of the patches above: it re-resolves the live
    repo root and runs the real stage. ``audio_preclean`` (the only
    ``SUBPROCESS_STAGES`` member) meant one execute test ran DeepFilterNet over
    the operator's source audio and wrote 1.5G into ``ASSETS/executions``.

    Session-scoped because the fork happens on a job thread that can outlive the
    test that started it, so a ``monkeypatch`` has often unwound by then. Narrow
    on purpose — only ``python -m interview_mux…`` trips it, which no test has a
    reason to spawn; ffmpeg and the model venvs are untouched.
    """
    import subprocess

    real_popen = subprocess.Popen

    class _GuardedPopen(real_popen):  # type: ignore[misc,valid-type]
        def __init__(self, args: Any, *pargs: Any, **kwargs: Any) -> None:
            command = _pipeline_module_spawn(args)
            if command is not None and not _ACTIVE_TEST["allow_pipeline_subprocess"]:
                _PIPELINE_SPAWNS.append(f"{_ACTIVE_TEST['nodeid']}: {command}")
                raise RuntimeError(
                    f"Tests must not fork the pipeline ({command}). The child ignores "
                    "fixtures and runs the real stage against the live ASSETS tree. "
                    "Patch JobRunner._stage_worker_cmd, or opt out with "
                    "@pytest.mark.allow_pipeline_subprocess."
                )
            super().__init__(args, *pargs, **kwargs)

    subprocess.Popen = _GuardedPopen  # type: ignore[misc]
    try:
        yield
    finally:
        subprocess.Popen = real_popen  # type: ignore[misc]


@pytest.fixture(autouse=True)
def attribute_pipeline_subprocess(
    request: pytest.FixtureRequest,
    block_pipeline_subprocess: None,
):
    """Fail the test that tried to fork — the raise lands on a job thread otherwise."""
    _ACTIVE_TEST["nodeid"] = request.node.nodeid
    _ACTIVE_TEST["allow_pipeline_subprocess"] = bool(
        request.node.get_closest_marker("allow_pipeline_subprocess")
    )
    seen = len(_PIPELINE_SPAWNS)
    try:
        yield
    finally:
        _ACTIVE_TEST["allow_pipeline_subprocess"] = False
    blocked = _PIPELINE_SPAWNS[seen:]
    if blocked:
        pytest.fail("Blocked pipeline subprocess spawn:\n  " + "\n  ".join(blocked))


@pytest.fixture(autouse=True)
def clear_write_staging_context() -> None:
    """ContextVar staging must not leak across tests (writes route into .pending_writes)."""
    from interview_mux.write_staging import exit_stage_staging

    exit_stage_staging()
    yield
    exit_stage_staging()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="run @pytest.mark.slow live-model tests (MusicGen weights, minutes each)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: live / long-running integration (MusicGen weights)")
    config.addinivalue_line("markers", "allow_network: permit outbound sockets")
    config.addinivalue_line(
        "markers", "real_executions_root: needs the live ASSETS/executions tree"
    )
    config.addinivalue_line(
        "markers", "allow_pipeline_subprocess: permit forking python -m interview_mux…"
    )


def _slow_enabled(config: pytest.Config) -> bool:
    return bool(config.getoption("--run-slow")) or str(
        os.environ.get("MUX_RUN_SLOW_TESTS") or ""
    ).strip().lower() in {"1", "true", "yes", "on"}


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """`slow` is opt-in: `--run-slow` or `MUX_RUN_SLOW_TESTS=1`.

    These tests load real MusicGen weights and generate audio. When the weights
    happen to be cached they do not skip and do not time out — they just run, for
    tens of minutes each, which makes a plain `pytest tests/` unusable. The
    existing `_musicgen_ready()` guards only skip when the weights are *missing*,
    so the better-provisioned the machine, the worse the suite behaves.

    Gating the marker rather than the individual tests keeps the capability
    tests intact and reachable on demand.
    """
    if _slow_enabled(config):
        return
    skip_slow = pytest.mark.skip(
        reason="live-model test: pass --run-slow or set MUX_RUN_SLOW_TESTS=1"
    )
    for item in items:
        if item.get_closest_marker("slow"):
            item.add_marker(skip_slow)
