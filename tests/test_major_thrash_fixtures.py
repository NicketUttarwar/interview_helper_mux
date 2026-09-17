"""Wave 10 thrash fixtures + dual-brain smoke (0.0.0 / 0.1.0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx

FIXTURES = Path(__file__).parent / "fixtures" / "thrash"


def _load_meta(name: str) -> dict:
    return json.loads((FIXTURES / name / "meta.json").read_text(encoding="utf-8"))


def _touch_wav(ctx: RunContext, *parts: str, size: int = 2048) -> None:
    path = ctx.final_path(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * (size - 4))


def _write_raw(ctx: RunContext, rel: str, data: dict) -> None:
    path = ctx.path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("brain", ["0.0.0", "0.1.0"])
def test_fixture_pending_master(tmp_path: Path, brain: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.delivery_invariants import committed_master_wav

    meta = _load_meta("pending_master")
    monkeypatch.setenv("MUX_HOMUNCULUS_VERSION", brain)
    ctx = isolated_run_ctx(tmp_path, f"fx_pending_{brain.replace('.', '')}")
    pending = ctx.run_dir / ".pending_writes" / "master_finalize" / "master" / "master.wav"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(b"RIFF" + b"\x00" * 2048)
    assert committed_master_wav(ctx) is meta["expect"]["committed_master_wav"]


@pytest.mark.parametrize("brain", ["0.0.0", "0.1.0"])
def test_fixture_synth_g1(tmp_path: Path, brain: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.delivery_invariants import resolve_g1_vo_open_resume

    meta = _load_meta("synth_g1")
    monkeypatch.setenv("MUX_HOMUNCULUS_VERSION", brain)
    ctx = isolated_run_ctx(tmp_path, f"fx_g1_{brain.replace('.', '')}")
    _write_raw(ctx, "understanding/gap_report.json", meta["gap_report"])
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails._g1_record_open",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.gates.check_g1_vo",
        lambda _ctx: ["vo_synth_001"],
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid == "vo_line_adjudicate",
    )
    assert resolve_g1_vo_open_resume(ctx) == meta["expect"]["resolve_g1_vo_open_resume"]


@pytest.mark.parametrize("brain", ["0.0.0", "0.1.0"])
def test_fixture_stale_autopsy(tmp_path: Path, brain: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.delivery_guardrails import ship_path_ready
    from interview_mux.homunculus.agenda import _junction_commitment_matches_assembly

    meta = _load_meta("stale_autopsy")
    monkeypatch.setenv("MUX_HOMUNCULUS_VERSION", brain)
    ctx = isolated_run_ctx(tmp_path, f"fx_autopsy_{brain.replace('.', '')}")
    _touch_wav(ctx, "master", "assembly.wav", size=int(meta["assembly_size"]))
    _write_raw(
        ctx,
        "master/seam_autopsy.json",
        {
            "commitment": {
                "status": "committed",
                "assembly": {"size": int(meta["commitment_size"])},
            }
        },
    )
    assert (
        _junction_commitment_matches_assembly(ctx)
        is meta["expect"]["junction_commitment_matches"]
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid in {"mix", "junction_snip_qa", "listen_delight_audit"},
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl",
        lambda _ctx: False,
    )
    ready, _ = ship_path_ready(ctx)
    assert ready is meta["expect"]["ship_path_ready"]


@pytest.mark.parametrize("brain", ["0.0.0", "0.1.0"])
def test_fixture_remutate_protect(
    tmp_path: Path, brain: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.delivery_guardrails import promote_complete_orphan_stage_done
    from interview_mux.homunculus.agenda import remaining_stages

    meta = _load_meta("remutate_protect")
    monkeypatch.setenv("MUX_HOMUNCULUS_VERSION", brain)
    ctx = isolated_run_ctx(tmp_path, f"fx_rem_{brain.replace('.', '')}")
    _write_raw(ctx, "mastering/listen_delight_remutate.json", meta["remutate"])
    _write_raw(ctx, "master/edl.json", {"clips": [{"segment_id": "seg_001"}]})
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.stage_outputs_present",
        lambda _ctx, sid: sid == "edl",
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.stage_artifact_incompleteness",
        lambda _ctx, sid: None,
    )
    promoted = promote_complete_orphan_stage_done(ctx, ("edl",))
    assert ("edl" in promoted) is meta["expect"]["orphan_promote_edl"]
    rem = remaining_stages(ctx, "delivery")
    assert ("edl" in rem) is meta["expect"]["remaining_includes_edl"]


@pytest.mark.parametrize("brain", ["0.0.0", "0.1.0"])
def test_fixture_driver_resume_honors_edl_narrative_remutate(
    tmp_path: Path, brain: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util

    from interview_mux.run_context import RunContext

    monkeypatch.setenv("MUX_HOMUNCULUS_VERSION", brain)
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path / "ASSETS"))
    ctx = RunContext(f"fx_driver_{brain.replace('.', '')}", create=True)
    driver_path = Path(__file__).resolve().parents[1] / "tools" / "full_auto_driver.py"
    spec = importlib.util.spec_from_file_location("full_auto_driver_fixture", driver_path)
    assert spec and spec.loader
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    _write_raw(
        ctx,
        "mastering/edl_narrative_remutate.json",
        {
            "attempt": 1,
            "max_attempts": 3,
            "from_stage": "edl",
            "from_stages": ["edl", "mix"],
            "exhausted": False,
        },
    )
    monkeypatch.setattr(driver, "RUN_ID", ctx.run_id)
    assert driver.delivery_resume_stage() == "edl"


@pytest.mark.parametrize("brain", ["0.0.0", "0.1.0"])
def test_fixture_driver_remutate_falls_through_when_producers_done(
    tmp_path: Path, brain: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once remutate producers are done, do not rewind to ranking for audit-only gap."""
    import importlib.util

    from interview_mux.run_context import RunContext

    monkeypatch.setenv("MUX_HOMUNCULUS_VERSION", brain)
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path / "ASSETS"))
    ctx = RunContext(f"fx_rem_fallthrough_{brain.replace('.', '')}", create=True)
    driver_path = Path(__file__).resolve().parents[1] / "tools" / "full_auto_driver.py"
    spec = importlib.util.spec_from_file_location("full_auto_driver_fallthrough", driver_path)
    assert spec and spec.loader
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    for sid in (
        "full_master_ranking",
        "transitions",
        "selection_framing_apply",
        "nugget_layup_compose",
        "vo_line_adjudicate",
        "vo_synthesize",
    ):
        (ctx.run_dir / ".stage_done" / sid).parent.mkdir(parents=True, exist_ok=True)
        (ctx.run_dir / ".stage_done" / sid).write_text("1\n", encoding="utf-8")
    _write_raw(
        ctx,
        "mastering/edl_narrative_remutate.json",
        {
            "attempt": 1,
            "max_attempts": 2,
            "from_stage": "full_master_ranking",
            "from_stages": [
                "full_master_ranking",
                "edl_narrative_audit",
                "transitions",
                "selection_framing_apply",
                "nugget_layup_compose",
                "vo_line_adjudicate",
                "vo_synthesize",
            ],
            "exhausted": False,
        },
    )
    # Minimal edl-ready so fall-through picks edl (not ranking).
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    _write_raw(ctx, "master/selection.json", {"ordered_segment_ids": ["seg_001"], "excluded_segment_ids": [], "chapters": []})
    _write_raw(ctx, "master/transitions.json", {"transitions": []})
    monkeypatch.setattr(driver, "RUN_ID", ctx.run_id)
    monkeypatch.setattr(driver, "_g1_vo_missing", lambda _ctx: False)
    monkeypatch.setattr(driver, "_edl_ready_artifacts", lambda _ctx: True)
    resume = driver.delivery_resume_stage()
    assert resume != "full_master_ranking"
    assert resume in {"edl", "edl_narrative_audit", "vo_synthesize"} or resume is not None

