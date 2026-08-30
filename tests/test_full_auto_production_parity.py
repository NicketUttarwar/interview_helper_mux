"""Full-auto production parity — no test-only quality waivers in driver env."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import full_auto_daemon_launch as dal  # noqa: E402

from interview_mux.post_master_quality import evaluate_post_master_quality  # noqa: E402

from run_fixtures import isolated_run_ctx  # noqa: E402


def _write_raw(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_driver_env_omits_stub_and_listenability_keys() -> None:
    env = dal._driver_env(
        port=8765,
        audio="ASSETS/input/interview.wav",
        keep_gui_server=True,
        partial_auto=False,
    )
    assert "MUX_E2E_MUSICGEN_ALLOW_STUB" not in env
    assert "MUX_E2E_SOFT_LISTENABILITY" not in env
    assert env.get("INTERVIEW_MUX_E2E_SOFT") == "1"


def test_pmq_soft_junction_requires_quality_waivers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_pmq_parity")
    master = ctx.path("master/master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF" + b"\0" * 40)
    ctx.write_json(
        "run_meta.json",
        {"e2e_soft_junction_residuals": True},
    )
    _write_raw(
        ctx,
        "master/seam_autopsy.json",
        {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00Z",
            "phase": "post_master",
            "commitment": {"status": "pending", "reasons": ["residual"]},
            "scores": {
                "continuity": 0.95,
                "finishability": 0.95,
                "information_clarity": 0.95,
                "music_completeness": 0.95,
                "sonic_density_fit": 0.9,
            },
            "seams": [],
            "blocking_reasons": [],
        },
    )

    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    monkeypatch.delenv("INTERVIEW_MUX_E2E_QUALITY_WAIVERS", raising=False)

    quality = evaluate_post_master_quality(ctx)
    seam = next(c for c in quality["checks"] if c["check_id"] == "seam_commitment")
    assert seam["passed"] is False

    monkeypatch.setenv("INTERVIEW_MUX_E2E_QUALITY_WAIVERS", "1")
    quality_waived = evaluate_post_master_quality(ctx)
    seam_waived = next(
        c for c in quality_waived["checks"] if c["check_id"] == "seam_commitment"
    )
    assert seam_waived["passed"] is True
