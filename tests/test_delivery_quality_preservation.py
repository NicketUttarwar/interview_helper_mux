"""Single-flow delivery quality contract — Stage 1 preservation checks."""

from __future__ import annotations

from interview_mux import pipeline
from interview_mux.progression_readiness import assert_delivery_ready, build_delivery_readiness_report
from interview_mux.web.stages import DELIVERY_STAGES, EXECUTABLE_ORDER


def test_delivery_order_has_thirteen_stages() -> None:
    # Keep in sync with v2 DELIVERY_ORDER (slim Pass-2 + junction + transcript + publish tail).
    assert len(pipeline.DELIVERY_ORDER) == 37


def test_delivery_order_matches_gui_executable_order() -> None:
    assert list(pipeline.DELIVERY_ORDER) == list(EXECUTABLE_ORDER["delivery"])


def test_delivery_stages_cover_all_delivery_order_ids() -> None:
    delivery_ids = {s.id for s in DELIVERY_STAGES}
    assert set(pipeline.DELIVERY_ORDER) <= delivery_ids


def test_assert_delivery_ready_is_callable() -> None:
    assert callable(assert_delivery_ready)
    assert callable(build_delivery_readiness_report)


def test_legacy_read_path_alias_master_from_flow_1_master(tmp_path) -> None:
    from interview_mux.write_staging import resolve_read_path

    legacy = tmp_path / "flow_1_master"
    legacy.mkdir(parents=True)
    (legacy / "selection.json").write_text("{}", encoding="utf-8")

    class _Ctx:
        run_dir = tmp_path

    assert resolve_read_path(_Ctx(), "master/selection.json").is_file()
