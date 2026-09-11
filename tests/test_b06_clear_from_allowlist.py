"""B-06: combined ANALYSIS+DELIVERY clear_from forbidden; heals via profiles."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from interview_mux.config import repo_root
from interview_mux.homunculus.agenda import invalidate_downstream
from interview_mux.publishability_boundary import (
    PublishabilityReport,
    PublishabilityViolation,
    write_publishability_repair_plan,
)
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER
from run_fixtures import isolated_run_ctx, mark_done_raw, patch_executions_root

_SRC = repo_root() / "src" / "interview_mux"


def _is_combined_order_expr(node: ast.AST) -> bool:
    """True for ``list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)``-style AST."""
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Add):
        return False

    def _order_name(n: ast.AST) -> str | None:
        if isinstance(n, ast.Name) and n.id in {"ANALYSIS_ORDER", "DELIVERY_ORDER"}:
            return n.id
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "list"
            and n.args
            and isinstance(n.args[0], ast.Name)
            and n.args[0].id in {"ANALYSIS_ORDER", "DELIVERY_ORDER"}
        ):
            return n.args[0].id
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "list"
            and n.args
            and isinstance(n.args[0], ast.Attribute)
            and n.args[0].attr in {"ANALYSIS_ORDER", "DELIVERY_ORDER"}
        ):
            return n.args[0].attr
        return None

    left = _order_name(node.left)
    right = _order_name(node.right)
    return {left, right} == {"ANALYSIS_ORDER", "DELIVERY_ORDER"}


def _combined_order_bindings(tree: ast.AST) -> set[str]:
    """Names assigned to ANALYSIS+DELIVERY concatenations in this module."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_combined_order_expr(node.value):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    bound.add(t.id)
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            if _is_combined_order_expr(node.value) and isinstance(node.target, ast.Name):
                bound.add(node.target.id)
    return bound


def test_ast_no_combined_clear_from_in_src() -> None:
    """Production src must never call clear_from with combined ANALYSIS+DELIVERY."""
    offenders: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "clear_from" not in text:
            continue
        tree = ast.parse(text, filename=str(path))
        bound = _combined_order_bindings(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_clear = (
                (isinstance(func, ast.Attribute) and func.attr == "clear_from")
                or (isinstance(func, ast.Name) and func.id == "clear_from")
            )
            if not is_clear or len(node.args) < 2:
                continue
            order_arg = node.args[1]
            if _is_combined_order_expr(order_arg):
                offenders.append(f"{path.relative_to(repo_root())}:{node.lineno}")
            elif isinstance(order_arg, ast.Name) and order_arg.id in bound:
                # Only flag if the binding is used as clear_from order in same file
                # and the assignment is literally combined (heal footgun).
                offenders.append(
                    f"{path.relative_to(repo_root())}:{node.lineno} ({order_arg.id})"
                )
    assert not offenders, "combined clear_from in src:\n" + "\n".join(offenders)


def test_clear_from_raises_on_combined_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("b06_combined", create=True)
    with pytest.raises(ValueError, match="combined ANALYSIS\\+DELIVERY"):
        ctx.clear_from("edl", list(ANALYSIS_ORDER) + list(DELIVERY_ORDER))


def test_clear_from_single_order_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("b06_single", create=True)
    mark_done_raw(ctx, "edl")
    mark_done_raw(ctx, "mix")
    ctx.clear_from("edl", list(DELIVERY_ORDER))
    assert not ctx.is_done("edl")


def test_invalidate_downstream_structural_uses_profile_not_clear_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "b06_inv")
    mark_done_raw(ctx, "edl")
    mark_done_raw(ctx, "mix")
    calls: list[Any] = []

    def _spy_clear(self: RunContext, stage: str, order: list[str], **kwargs: Any) -> None:
        calls.append((stage, list(order)))
        raise AssertionError("clear_from must not be called from structural invalidate")

    monkeypatch.setattr(RunContext, "clear_from", _spy_clear)
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.invalidation_is_structural",
        lambda _ctx, _stage: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.delivery_epoch_locked",
        lambda _ctx: False,
    )
    applied: list[str] = []

    def _spy_apply(ctx: Any, profile_id: str, *, reason: str = "") -> dict[str, Any]:
        applied.append(profile_id)
        return {"profile_id": profile_id, "cleared": ["edl", "mix"], "forbidden_skipped": []}

    monkeypatch.setattr(
        "interview_mux.execution_invalidation_profiles.apply_bounded_invalidation",
        _spy_apply,
    )
    out = invalidate_downstream(ctx, "edl")
    assert out.get("ok") is True
    assert applied == ["structural_delivery"] or applied
    assert "structural" in str(out.get("mode") or "structural")
    assert not calls


def test_invalidate_downstream_heal_only_skips_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "b06_heal")
    mark_done_raw(ctx, "nugget_layup_compose")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.invalidation_is_structural",
        lambda _ctx, _stage: False,
    )
    applied: list[str] = []

    def _spy_apply(ctx: Any, profile_id: str, *, reason: str = "") -> dict[str, Any]:
        applied.append(profile_id)
        return {"profile_id": profile_id, "cleared": []}

    monkeypatch.setattr(
        "interview_mux.execution_invalidation_profiles.apply_bounded_invalidation",
        _spy_apply,
    )
    out = invalidate_downstream(ctx, "nugget_layup_compose")
    assert out.get("mode") == "heal_only"
    assert applied == []


def test_publishability_hard_repair_never_combined_clear_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "b06_pub")
    calls: list[Any] = []

    def _spy_clear(self: RunContext, stage: str, order: list[str], **kwargs: Any) -> None:
        calls.append((stage, list(order)))

    monkeypatch.setattr(RunContext, "clear_from", _spy_clear)
    applied: list[str] = []

    def _spy_apply(ctx: Any, profile_id: str, *, reason: str = "") -> dict[str, Any]:
        applied.append(profile_id)
        return {"profile_id": profile_id, "cleared": ["edl"], "forbidden_skipped": []}

    monkeypatch.setattr(
        "interview_mux.execution_invalidation_profiles.apply_bounded_invalidation",
        _spy_apply,
    )
    report = PublishabilityReport(
        checkpoint="post_edl",
        ok=False,
        violations=[
            PublishabilityViolation(
                error_class="never_touch_zeroed_keep",
                code="zero_duration_speech",
                detail="seg_x",
                segment_id="seg_x",
            )
        ],
    )
    playbook = MagicMock()
    playbook.resume_stage = "edl"
    plan = write_publishability_repair_plan(ctx, report, playbook=playbook, soft=False)
    assert applied
    assert plan.get("invalidation_profile")
    assert not any(
        set(ANALYSIS_ORDER) & set(order) and set(DELIVERY_ORDER) & set(order)
        for _stage, order in calls
    )


def test_combined_clear_hatch_requires_pytest_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MUX_ALLOW_COMBINED_CLEAR alone is not enough outside pytest."""
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("b06_hatch", create=True)
    monkeypatch.setenv("MUX_ALLOW_COMBINED_CLEAR", "1")
    RunContext._ALLOW_COMBINED_CLEAR = False  # type: ignore[attr-defined]
    # Explicit hatch + pytest session → allowed (no raise).
    ctx.clear_from("edl", list(ANALYSIS_ORDER) + list(DELIVERY_ORDER))
    # Without hatch flag, still refused even under pytest.
    monkeypatch.delenv("MUX_ALLOW_COMBINED_CLEAR", raising=False)
    with pytest.raises(ValueError, match="combined ANALYSIS\\+DELIVERY"):
        ctx.clear_from("edl", list(ANALYSIS_ORDER) + list(DELIVERY_ORDER))
    # Hatch alone is insufficient when not in a pytest session.
    monkeypatch.setenv("MUX_ALLOW_COMBINED_CLEAR", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert RunContext._combined_clear_allowed() is False
