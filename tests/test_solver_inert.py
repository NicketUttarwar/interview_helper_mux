"""Authority removal ratchet: no solver reorder hook, env, or API remains."""

from __future__ import annotations

from pathlib import Path

SRC = Path("src/interview_mux")
FRONTEND = Path("frontend/src")
TOOLS = Path("tools")
DOCS = Path("docs")
ROOT_DOCS = (Path("AGENTS.md"), Path("NORTH_STAR.md"))

FORBIDDEN = (
    "MUX_SOLVER_AUTHORITATIVE",
    "MUX_SOLVER_SHADOW",
    "authoritative_sequence",
    "SolverHaltPanel",
    "solver-decision",
    "solver_authoritative",
)


def test_solver_module_is_gone() -> None:
    assert not (SRC / "solver.py").exists()


def test_solver_replay_tool_is_gone() -> None:
    assert not (TOOLS / "solver_replay.py").exists()


def test_halt_panel_and_decision_utils_are_gone() -> None:
    assert not (FRONTEND / "components/workspace/SolverHaltPanel.tsx").exists()
    assert not (FRONTEND / "utils/solverDecision.ts").exists()


def test_no_forbidden_tokens_in_live_surfaces() -> None:
    roots = [SRC, FRONTEND, TOOLS, DOCS, *ROOT_DOCS]
    hits: list[str] = []
    for root in roots:
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for path in paths:
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".ts", ".tsx", ".md", ".sh", ".yaml", ".yml", ".json"}:
                continue
            # HISTORY footnote + retired stubs may name the removed flag once.
            if path.name in {
                "mastering-homunculus.md",
                "solver-promotion-d14-runbook.md",
                "solver-replay-validation.md",
            }:
                continue
            # Archival plan body kept for history.
            if "solver_brain_020.plan.md" in str(path):
                continue
            # Built GUI bundles — refresh via build_gui.sh; source is ratcheted above.
            if "web/static" in str(path).replace("\\", "/"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for token in FORBIDDEN:
                if token in text:
                    hits.append(f"{path}:{token}")
    assert hits == [], hits


def test_walk_sequence_is_always_seed_order(tmp_path: Path, monkeypatch) -> None:
    from interview_mux.homunculus.agenda import _walk_sequence
    from interview_mux.run_context import RunContext
    from run_fixtures import isolated_run_ctx

    monkeypatch.delenv("MUX_SOLVER_AUTHORITATIVE", raising=False)
    ctx: RunContext = isolated_run_ctx(tmp_path, "seed_only")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "run_mode": "full-auto", "full_auto": True},
        skip_handoff=True,
    )
    stages = ["ingest", "transcribe", "speaker_roles"]
    assert list(_walk_sequence(ctx, stages, reason="test")) == stages


def test_brains_public_hides_legacy_010() -> None:
    from interview_mux.homunculus.version import brains_public, list_brains

    ids = {b["id"] for b in brains_public()}
    assert "0.2.0" in ids
    assert "0.0.0" in ids
    assert "0.1.0" not in ids
    assert any(b.id == "0.1.0" for b in list_brains())
