"""Partially-accelerated run mode — guardrails on G0 and S3 only."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))


def test_normalize_run_mode_partial_aliases() -> None:
    from interview_mux.full_auto_launch import normalize_run_mode

    assert normalize_run_mode("partial-auto") == "partially-accelerated"
    assert normalize_run_mode("partially_accelerated") == "partially-accelerated"
    assert normalize_run_mode("manual") == "manual"
    assert normalize_run_mode("full-auto") == "full-auto"


def test_normalize_run_mode_manual_default() -> None:
    from interview_mux.full_auto_launch import normalize_run_mode

    assert normalize_run_mode(None) == "manual"
    assert normalize_run_mode("") == "manual"


def test_is_partial_auto_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import full_auto_driver as driver

    monkeypatch.setenv("MUX_PARTIAL_AUTO", "1")
    driver._PARTIAL_AUTO = None
    assert driver.is_partial_auto() is True
    driver._PARTIAL_AUTO = None
    monkeypatch.delenv("MUX_PARTIAL_AUTO", raising=False)
    assert driver.is_partial_auto() is False


def test_complete_g0_skipped_when_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    import full_auto_driver as driver

    monkeypatch.setattr(driver, "is_partial_auto", lambda: True)
    called: list[tuple] = []

    def fake_api(method: str, path: str, body=None, timeout=60):  # type: ignore[no-untyped-def]
        called.append((method, path, body))
        return {}

    monkeypatch.setattr(driver, "api", fake_api)
    driver.complete_g0()
    assert called == []


def test_complete_g0_runs_when_full_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    import full_auto_driver as driver

    monkeypatch.setattr(driver, "is_partial_auto", lambda: False)
    driver.RUN_ID = "exec_test_partial"
    called: list[tuple] = []

    def fake_api(method: str, path: str, body=None, timeout=60):  # type: ignore[no-untyped-def]
        called.append((method, path, body))
        return {}

    monkeypatch.setattr(driver, "api", fake_api)
    driver.complete_g0()
    assert len(called) == 1
    assert called[0][0] == "POST"
    assert "transcript-review/complete" in called[0][1]


def test_finish_complete_run_partial_skips_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    import full_auto_driver as driver

    monkeypatch.setattr(driver, "is_partial_auto", lambda: True)
    monkeypatch.setattr(driver, "assert_fresh_layer_contract", lambda: None)
    monkeypatch.setattr(driver, "wait_for_operator_g_publish", lambda: True)
    monkeypatch.setattr(driver, "finish_partial_complete_run", lambda: 0)
    sync_called: list[bool] = []

    def fake_sync() -> dict:
        sync_called.append(True)
        return {}

    monkeypatch.setattr(driver, "sync_publish_to_s3", fake_sync)
    assert driver.finish_complete_run() == 0
    assert sync_called == []


def test_finish_complete_run_full_auto_syncs(monkeypatch: pytest.MonkeyPatch) -> None:
    import full_auto_driver as driver

    monkeypatch.setattr(driver, "is_partial_auto", lambda: False)
    monkeypatch.setattr(driver, "assert_fresh_layer_contract", lambda: None)
    monkeypatch.setattr(driver, "write_full_auto_status", lambda **_: None)
    monkeypatch.setattr(driver, "summarize_decisions", lambda **_: None)
    monkeypatch.setattr(driver, "_write_terminal_report", lambda **_: None)
    monkeypatch.setattr(driver, "_keep_gui_server", lambda: True)
    monkeypatch.setattr(driver, "MASTER", MagicMock(is_file=lambda: True, stat=lambda: MagicMock(st_size=9999)))

    sync_called: list[bool] = []

    def fake_sync() -> dict:
        sync_called.append(True)
        return {"uploaded": True}

    monkeypatch.setattr(driver, "sync_publish_to_s3", fake_sync)

    with patch("full_auto_daemon_launch.shutdown_full_auto_stack", return_value={}):
        driver.finish_complete_run()
    assert sync_called == [True]


def test_write_terminal_report_logs_invariant_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import full_auto_driver as driver

    from interview_mux.run_context import RunContext

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path / "ASSETS"))
    ctx = RunContext("exec_invariant_summary", create=True)
    path = ctx.final_path("operator", "invariant_heals.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"kind":"seed_cycle_detected"}\n', encoding="utf-8")
    monkeypatch.setattr(driver, "RUN_ID", ctx.run_id)
    logs: list[str] = []
    monkeypatch.setattr(driver, "log", lambda msg: logs.append(str(msg)))

    with patch(
        "interview_mux.execution_report.write_execution_report",
        return_value={"run_dir": str(ctx.run_dir), "ship": {"master": {"present": False}}},
    ):
        driver._write_terminal_report(
            outcome="halted_needs_operator",
            halt_stage="transitions",
            root_cause="fixture",
        )

    assert any("[INVARIANT summary]" in line for line in logs)


def test_g_publish_operator_done_detects_upload() -> None:
    import full_auto_driver as driver

    driver.RUN_ID = "exec_abc"
    assert driver._g_publish_operator_done({"skipped": True}) is True
    assert driver._g_publish_operator_done({"already_uploaded_count": 1}) is True
    assert driver._g_publish_operator_done({"pending": True}) is False


def test_automation_driver_run_includes_partial_and_full() -> None:
    from interview_mux.automation_run import (
        PARTIAL_MAY_PAUSE_GATES,
        PARTIAL_MUST_ACT_GATES,
        automation_driver_run,
        is_full_auto_run,
        is_partially_accelerated_run,
    )

    assert is_partially_accelerated_run(
        {"run_mode": "partially-accelerated", "partial_auto": True}
    )
    assert is_full_auto_run({"run_mode": "full-auto", "full_auto": True})
    assert automation_driver_run({"run_mode": "partially-accelerated", "partial_auto": True})
    assert automation_driver_run({"run_mode": "full-auto", "full_auto": True})
    assert not automation_driver_run({"run_mode": "manual"})
    # D-01 SSOT
    assert PARTIAL_MUST_ACT_GATES == ("transcript_review", "g_publish")
    assert "gap_framing" in PARTIAL_MAY_PAUSE_GATES
    assert "g1_vo_pickup" in PARTIAL_MAY_PAUSE_GATES


def test_partial_never_syncs_s3_without_g_publish_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-06 / GATE-GPUB: Partial finish path never calls sync without operator wait."""
    import full_auto_driver as driver

    monkeypatch.setattr(driver, "is_partial_auto", lambda: True)
    monkeypatch.setattr(driver, "assert_fresh_layer_contract", lambda: None)

    wait_called: list[bool] = []

    def fake_wait() -> bool:
        wait_called.append(True)
        return False  # operator never consented / timed out

    sync_called: list[bool] = []

    def fake_sync() -> dict:
        sync_called.append(True)
        return {}

    monkeypatch.setattr(driver, "wait_for_operator_g_publish", fake_wait)
    monkeypatch.setattr(driver, "sync_publish_to_s3", fake_sync)
    monkeypatch.setattr(driver, "finish_partial_complete_run", lambda: 0)
    # When wait returns False, finish_complete_run should not sync.
    # Driver may return non-zero; still must not sync.
    try:
        driver.finish_complete_run()
    except Exception:
        pass
    assert wait_called == [True]
    assert sync_called == []


def test_recommended_framing_honors_llm_no_and_sparse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-07 / SYN-GFR: never auto-Yes over explicit LLM no/sparse."""
    from interview_mux.homunculus.gates import recommended_framing_action, set_gate_decision
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "framing_posture_d07")
    ctx.write_json(
        "understanding/source_topology.json",
        {"topology_class": "one_on_one_balanced", "pickup_eligible_speaker_id": "spk_1"},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/framing_posture_decision.json",
        {"recommended_framing": "no", "rationale": "fixture"},
        skip_handoff=True,
    )
    assert recommended_framing_action(ctx) == "skip"

    ctx.write_json(
        "understanding/framing_posture_decision.json",
        {"recommended_framing": "sparse", "rationale": "fixture"},
        skip_handoff=True,
    )
    assert recommended_framing_action(ctx) == "present_operator"

    # Operator sticky wins over LLM
    set_gate_decision(ctx, "framing_consent", "auto_resolve")
    assert recommended_framing_action(ctx) == "auto_resolve"


def test_unattended_defaults_enabled_for_partial_run_meta(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from interview_mux.stage_resilience import unattended_defaults_enabled
    from run_fixtures import isolated_run_ctx

    for key in (
        "MUX_FULL_AUTO",
        "MUX_PARTIAL_AUTO",
        "MUX_RUN_MODE",
        "INTERVIEW_MUX_AUTO_ACCEPT_GATES",
    ):
        monkeypatch.delenv(key, raising=False)
    ctx = isolated_run_ctx(tmp_path, "exec_partial_unattended")
    ctx.write_json(
        "run_meta.json",
        {"run_mode": "partially-accelerated", "partial_auto": True},
    )
    assert unattended_defaults_enabled(ctx) is True


def test_listen_delight_waiver_unattended_partial_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import (
        ensure_listen_delight_waiver_unattended,
        listen_delight_waived_unattended,
    )
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "ld_waiver_partial")
    ctx.write_json(
        "run_meta.json",
        {"run_mode": "partially-accelerated", "partial_auto": True},
    )
    audit_path = ctx.path("mastering/listen_delight_audit.json")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        '{"status":"complete","scores":{}}',
        encoding="utf-8",
    )
    assert ensure_listen_delight_waiver_unattended(ctx) is True
    assert listen_delight_waived_unattended(ctx) is True

