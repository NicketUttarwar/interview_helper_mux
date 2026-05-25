from __future__ import annotations

from interview_mux.config import load_defaults, merged_config, repo_root
from interview_mux.run_context import RunContext


def test_repo_root_exists():
    assert (repo_root() / "docs" / "pipeline.md").is_file()


def test_defaults_have_models():
    cfg = load_defaults()
    assert "models" in cfg
    assert cfg["models"]["speaker_roles"]


def test_run_context_allocate(tmp_path, monkeypatch):
    monkeypatch.chdir(repo_root())
    ctx = RunContext("run_099")
    assert ctx.run_dir.name == "run_099"
    assert ctx.path("ingest").parent == ctx.run_dir
