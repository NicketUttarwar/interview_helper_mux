"""exec_13170: automation must rewrite premature_cap pins, not idle-spin.

When full-auto requests from_stage=edl while sound_design_vo_finalize is still
the producer, JobRunner used to return HTTP 200 + ok:False/pinned_to without
starting a worker. The driver treated that as a successful execute and then
saw idle forever.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.web.runner import JobRunner
from run_fixtures import isolated_run_ctx


def test_automation_rewrites_premature_cap_instead_of_hard_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "i6_premature_rewrite")
    ctx.write_json(
        "run_meta.json",
        {
            "execution_id": ctx.run_id,
            "run_mode": "full-auto",
            "full_auto": True,
        },
        skip_handoff=True,
    )

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.premature_cap_hard_pin",
        lambda _ctx, resume, message="": "sound_design_vo_finalize",
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime._seed_prereq_block",
        lambda _ctx, resume: None,
    )
    # _preflight_and_spawn builds its own RunContext(run_id) under ASSETS —
    # force automation path + bind that ctx to the isolated fixture.
    monkeypatch.setattr(
        "interview_mux.automation_run.automation_driver_run",
        lambda _meta: True,
    )
    monkeypatch.setattr(
        "interview_mux.web.runner.RunContext",
        lambda run_id, create=False: ctx,
    )
    monkeypatch.setattr(
        "interview_mux.web.runner.check_stage_reuse_before_execute",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        JobRunner,
        "_check_api_consent",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        JobRunner,
        "_preflight_delivery_dispatch",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        JobRunner,
        "_stages_for_execute",
        lambda *_a, **_k: ["sound_design_vo_finalize", "edl"],
    )

    captured: dict[str, object] = {}

    def _spawn(self, run_id, **kwargs):  # type: ignore[no-untyped-def]
        captured["run_id"] = run_id
        captured.update(kwargs)

    monkeypatch.setattr(JobRunner, "_spawn_pipeline_thread", _spawn)

    runner = JobRunner()
    assert runner._reserve_pipeline_start(ctx.run_id)
    try:
        result = runner._preflight_and_spawn(
            ctx.run_id,
            mode="delivery",
            from_stage="edl",
            api_consents={"local": True, "openai": True},
        )
    finally:
        runner._clear_pipeline_start_reservation(ctx.run_id)

    assert result.get("ok") is True, result
    assert result.get("pinned_to") is None
    # Leapfrog B+: premature_cap lands via admit_resume (clamp, not leapfrog).
    from interview_mux.heal_pin_authority import admit_resume

    expected = admit_resume(
        ctx,
        "sound_design_vo_finalize",
        current="edl",
        intent="premature_cap",
    )
    assert captured.get("from_stage") == expected


def test_gui_still_hard_fails_premature_cap_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "i6_gui_hard_fail")
    ctx.write_json(
        "run_meta.json",
        {"execution_id": ctx.run_id, "run_mode": "interactive"},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.premature_cap_hard_pin",
        lambda _ctx, resume, message="": "sound_design_vo_finalize",
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.runtime._seed_prereq_block",
        lambda _ctx, resume: None,
    )
    monkeypatch.setattr(
        "interview_mux.automation_run.automation_driver_run",
        lambda _meta: False,
    )
    monkeypatch.setattr(
        "interview_mux.web.runner.RunContext",
        lambda run_id, create=False: ctx,
    )
    monkeypatch.setattr(
        "interview_mux.web.runner.check_stage_reuse_before_execute",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        JobRunner,
        "_check_api_consent",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        JobRunner,
        "_stages_for_execute",
        lambda *_a, **_k: ["edl"],
    )

    runner = JobRunner()
    assert runner._reserve_pipeline_start(ctx.run_id)
    try:
        result = runner._preflight_and_spawn(
            ctx.run_id,
            mode="delivery",
            from_stage="edl",
            api_consents={"local": True, "openai": True},
        )
    finally:
        runner._clear_pipeline_start_reservation(ctx.run_id)

    assert result.get("ok") is False
    from interview_mux.heal_pin_authority import admit_resume

    expected = admit_resume(
        ctx,
        "sound_design_vo_finalize",
        current="edl",
        intent="premature_cap",
    )
    assert result.get("pinned_to") == expected
