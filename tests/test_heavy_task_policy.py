"""Unit tests for heavy-task kill detection, abort backoff, and §0.3b reclaim."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.heavy_task_policy import (
    abort_backoff_sec,
    bind_reclaim_run,
    clear_reclaim_retry_state,
    is_heavy_kill_returncode,
    is_reclaim_worthy_failure,
    reclaim_for_same_class_retry,
    reclaim_settle_sec,
    record_heavy_abort,
    wait_abort_backoff,
)


def test_is_heavy_kill_returncode() -> None:
    assert is_heavy_kill_returncode(-15)
    assert is_heavy_kill_returncode(-9)
    assert is_heavy_kill_returncode(-6)
    assert is_heavy_kill_returncode(134)
    assert not is_heavy_kill_returncode(0)
    assert not is_heavy_kill_returncode(1)
    assert not is_heavy_kill_returncode(None)


def test_abort_backoff_sec_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTERVIEW_MUX_GPU_ABORT_BACKOFF_SEC", raising=False)
    assert abort_backoff_sec() == 30.0


def test_reclaim_settle_sec_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTERVIEW_MUX_LOCAL_ML_RECLAIM_SETTLE_SEC", raising=False)
    assert reclaim_settle_sec() == 5.0


def test_is_reclaim_worthy_failure_filters_deterministic() -> None:
    assert is_reclaim_worthy_failure(returncode=-9, stderr="timeout after 600s")
    assert is_reclaim_worthy_failure(returncode=-15)
    assert is_reclaim_worthy_failure(returncode=1, stderr="CUDA OOM")
    assert is_reclaim_worthy_failure(exception=RuntimeError("MPS backend out of memory"))
    assert not is_reclaim_worthy_failure(returncode=1, stderr="invalid argument: bad model")
    assert not is_reclaim_worthy_failure(returncode=2, stderr="")


def test_reclaim_for_same_class_retry_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """§0.3b: first reclaim sleeps settle; second same fingerprint returns False."""
    import interview_mux.heavy_task_policy as htp

    sleeps: list[float] = []
    monkeypatch.setattr(htp.time, "sleep", lambda s: sleeps.append(float(s)))
    monkeypatch.setattr(htp, "_state_path", lambda: tmp_path / "state.json")
    monkeypatch.setenv("INTERVIEW_MUX_LOCAL_ML_RECLAIM_SETTLE_SEC", "5")
    clear_reclaim_retry_state()

    assert (
        reclaim_for_same_class_retry(
            consumer="musicgen", fingerprint="large:ladder", returncode=-9
        )
        is True
    )
    assert sleeps == [5.0]
    assert (
        reclaim_for_same_class_retry(
            consumer="musicgen", fingerprint="large:ladder", returncode=-9
        )
        is False
    )
    assert len(sleeps) == 1
    assert (
        reclaim_for_same_class_retry(
            consumer="musicgen", fingerprint="medium:ladder", returncode=-9
        )
        is True
    )
    assert sleeps == [5.0, 5.0]


def test_reclaim_skips_deterministic_without_sleep(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import interview_mux.heavy_task_policy as htp

    sleeps: list[float] = []
    monkeypatch.setattr(htp.time, "sleep", lambda s: sleeps.append(float(s)))
    monkeypatch.setattr(htp, "_state_path", lambda: tmp_path / "state.json")
    clear_reclaim_retry_state()

    assert (
        reclaim_for_same_class_retry(
            consumer="speech",
            fingerprint="stt:a.wav",
            returncode=1,
            stderr="invalid audio path",
        )
        is False
    )
    assert sleeps == []


def test_reclaim_settle_suppresses_abort_backoff_stack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reclaim settle must not stack with ~30s wait_abort_backoff."""
    import interview_mux.heavy_task_policy as htp

    sleeps: list[float] = []
    monkeypatch.setattr(htp.time, "sleep", lambda s: sleeps.append(float(s)))
    monkeypatch.setattr(htp, "_state_path", lambda: tmp_path / "state.json")
    monkeypatch.setenv("INTERVIEW_MUX_LOCAL_ML_RECLAIM_SETTLE_SEC", "5")
    monkeypatch.setenv("INTERVIEW_MUX_GPU_ABORT_BACKOFF_SEC", "30")
    clear_reclaim_retry_state()

    record_heavy_abort("musicgen", -15, stage="musicgen")
    assert reclaim_for_same_class_retry(
        consumer="musicgen", fingerprint="kill:once", returncode=-15
    )
    assert sleeps == [5.0]
    # Post-settle abort backoff must be credited away.
    assert wait_abort_backoff(consumer="chatterbox") == 0.0
    assert len(sleeps) == 1


def test_reclaim_no_synthetic_abort_on_soft_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import interview_mux.heavy_task_policy as htp

    monkeypatch.setattr(htp.time, "sleep", lambda s: None)
    monkeypatch.setattr(htp, "_state_path", lambda: tmp_path / "state.json")
    monkeypatch.setenv("INTERVIEW_MUX_LOCAL_ML_RECLAIM_SETTLE_SEC", "5")
    clear_reclaim_retry_state()

    assert reclaim_for_same_class_retry(
        consumer="mmaudio",
        fingerprint="soft",
        returncode=1,
        stderr="CUDA out of memory",
    )
    doc = htp._read_state()
    # Soft OOM rc=1 must not invent a kill abort timestamp.
    assert not doc.get("last_abort_at")
    assert doc.get("last_reclaim_settle_at")
    assert doc.get("abort_backoff_credited_by") == "reclaim_settle"


def test_bind_reclaim_run_resets_fingerprints(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import interview_mux.heavy_task_policy as htp

    monkeypatch.setattr(htp.time, "sleep", lambda s: None)
    monkeypatch.setattr(htp, "_state_path", lambda: tmp_path / "state.json")
    clear_reclaim_retry_state()

    assert reclaim_for_same_class_retry(
        consumer="musicgen", fingerprint="x", returncode=-9
    )
    assert (
        reclaim_for_same_class_retry(consumer="musicgen", fingerprint="x", returncode=-9)
        is False
    )
    bind_reclaim_run("exec_999_new")
    assert reclaim_for_same_class_retry(
        consumer="musicgen", fingerprint="x", returncode=-9
    )


def test_reclaim_does_not_kill_completed_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import interview_mux.heavy_task_policy as htp

    killed: list[object] = []

    class Done:
        returncode = -9
        stderr = "timeout after 10s"

        def poll(self) -> int:
            return -9

    monkeypatch.setattr(htp.time, "sleep", lambda s: None)
    monkeypatch.setattr(htp, "_state_path", lambda: tmp_path / "state.json")

    def fake_kill(proc: object, **_kw: object) -> None:
        killed.append(proc)

    monkeypatch.setattr(
        "interview_mux.hang_escalation.kill_process_tree", fake_kill, raising=False
    )
    # Import path used inside reclaim — patch on hang_escalation module after import.
    import interview_mux.hang_escalation as he

    monkeypatch.setattr(he, "kill_process_tree", fake_kill)
    clear_reclaim_retry_state()

    assert reclaim_for_same_class_retry(
        consumer="mmaudio", fingerprint="done", proc=Done(), returncode=-9
    )
    assert killed == []


def test_record_and_wait_abort_backoff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import interview_mux.heavy_task_policy as htp

    sleeps: list[float] = []
    monkeypatch.setattr(htp.time, "sleep", lambda s: sleeps.append(float(s)))
    monkeypatch.setattr(htp, "_state_path", lambda: tmp_path / "state.json")
    monkeypatch.setenv("INTERVIEW_MUX_GPU_ABORT_BACKOFF_SEC", "30")
    clear_reclaim_retry_state()
    # Ensure no stale reclaim credit.
    path = tmp_path / "state.json"
    if path.is_file():
        path.unlink()

    record_heavy_abort("musicgen", -15, stage="musicgen")
    slept = wait_abort_backoff(consumer="chatterbox")
    assert slept > 0
    assert sleeps and sleeps[0] > 0


def test_wait_abort_backoff_no_recent_abort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import interview_mux.heavy_task_policy as htp

    monkeypatch.setattr(htp, "_state_path", lambda: tmp_path / "state.json")
    monkeypatch.setattr(
        htp.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError("should not sleep"))
    )
    clear_reclaim_retry_state()
    assert wait_abort_backoff() == 0.0


def test_is_abort_returncode_delegates() -> None:
    from interview_mux.musicgen_runner import is_abort_returncode

    assert is_abort_returncode(-15)
    assert is_abort_returncode(-6)


def test_mmaudio_style_reclaim_before_fidelity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Simulate MMAudio loop: hang → reclaim once (same variant) → then fidelity step."""
    import interview_mux.heavy_task_policy as htp
    from interview_mux.hang_escalation import MMAUDIO_FIDELITY_RUNGS, next_fidelity_rung

    clear_reclaim_retry_state()
    sleeps: list[float] = []
    monkeypatch.setattr(htp.time, "sleep", lambda s: sleeps.append(float(s)))
    monkeypatch.setattr(htp, "_state_path", lambda: tmp_path / "state.json")
    monkeypatch.setenv("INTERVIEW_MUX_LOCAL_ML_RECLAIM_SETTLE_SEC", "5")

    variants_seen: list[str] = []
    resolved = "large_44k_v2"
    tried = [resolved]
    attempts = 0
    while attempts < 6:
        attempts += 1
        variants_seen.append(resolved)
        rc = -9 if attempts < 3 else 0
        if rc == 0:
            break
        if reclaim_for_same_class_retry(
            consumer="mmaudio",
            fingerprint=f"{resolved}:a1",
            returncode=rc,
            stderr="timeout after 900s",
        ):
            continue
        nxt = next_fidelity_rung(resolved, MMAUDIO_FIDELITY_RUNGS)
        if nxt and nxt not in tried:
            tried.append(nxt)
            resolved = nxt
            continue
        break

    assert sleeps == [5.0]
    assert variants_seen[:2] == ["large_44k_v2", "large_44k_v2"]
    assert variants_seen[2] == "large_44k"
