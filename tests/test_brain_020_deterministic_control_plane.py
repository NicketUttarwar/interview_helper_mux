"""0.2.0 — deterministic control plane brain: registered, default, conductor-free.

The turn budget existed because the LLM owned control flow. 0.2.0 keeps every
homunculus rail (ledger, admit, dispatch budget) and hands stage selection to the
seed walk, so ``is_homunculus_brain`` must stay True while
``llm_owns_control_flow`` goes False.
"""

from __future__ import annotations

from pathlib import Path

from interview_mux.homunculus import version as brain_version
from interview_mux.homunculus.runtime import conductor_owns_control_flow, is_homunculus_run
from run_fixtures import isolated_run_ctx


def test_020_is_registered_and_highest() -> None:
    ids = [b.id for b in brain_version.list_brains()]
    assert "0.2.0" in ids
    assert brain_version.highest_version() == "0.2.0"


def test_020_is_the_default() -> None:
    assert brain_version.default_version() == "0.2.0"
    assert brain_version.normalize_version("latest") == "0.2.0"
    default_rows = [b for b in brain_version.brains_public() if b["is_default"]]
    assert [b["id"] for b in default_rows] == ["0.2.0"]


def test_020_keeps_homunculus_rails_but_not_llm_control_flow() -> None:
    # The footgun this guards: a new `kind` would flip is_homunculus_brain False
    # at every is_homunculus_run site, silently dropping the dispatch ledger.
    assert brain_version.is_homunculus_brain("0.2.0") is True
    assert brain_version.resolve_brain("0.2.0").kind == "homunculus"
    assert brain_version.llm_owns_control_flow("0.2.0") is False
    assert brain_version.llm_owns_control_flow("0.1.0") is True
    assert brain_version.llm_owns_control_flow("0.0.0") is False


def test_brains_public_exposes_control_plane() -> None:
    rows = {b["id"]: b for b in brain_version.brains_public()}
    assert rows["0.1.0"]["control_plane"] == "llm"
    assert rows["0.2.0"]["control_plane"] == "deterministic"


def test_runtime_predicates_on_a_020_run(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "brain020")
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "homunculus_kind": "homunculus",
            "homunculus_control_plane": "deterministic",
        },
        skip_handoff=True,
    )
    assert is_homunculus_run(ctx) is True
    assert conductor_owns_control_flow(ctx) is False


def test_runtime_predicates_on_a_010_run(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "brain010")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    assert is_homunculus_run(ctx) is True
    assert conductor_owns_control_flow(ctx) is True


def test_stamp_run_meta_records_control_plane(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "brain020stamp")
    vid = brain_version.stamp_run_meta(ctx, "0.2.0")
    assert vid == "0.2.0"
    meta = ctx.read_json("run_meta.json") or {}
    assert meta["homunculus_version"] == "0.2.0"
    assert meta["homunculus_kind"] == "homunculus"
    assert meta["homunculus_control_plane"] == "deterministic"


def test_020_never_calls_the_conductor(tmp_path: Path, monkeypatch) -> None:
    """The load-bearing assertion: no conductor turn is spent on 0.2.0."""
    from interview_mux.homunculus import agenda

    ctx = isolated_run_ctx(tmp_path, "brain020noconductor")
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.2.0",
            "homunculus_kind": "homunculus",
            "homunculus_control_plane": "deterministic",
        },
        skip_handoff=True,
    )

    def _boom(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("run_conductor called on a deterministic brain")

    monkeypatch.setattr("interview_mux.homunculus.loop.run_conductor", _boom)

    walked: list[list[str]] = []
    monkeypatch.setattr(
        agenda,
        "walk_seed_agenda",
        lambda _ctx, stages, **kw: walked.append(list(stages)),
    )

    out = agenda.run_homunculus_phase(
        ctx, "analysis", ["content_context", "talking_points_compose"], client=object()
    )
    assert out["conductor"]["skipped"] == "deterministic_control_plane"
    assert walked, "deterministic brain must hand analysis to the seed walk"
