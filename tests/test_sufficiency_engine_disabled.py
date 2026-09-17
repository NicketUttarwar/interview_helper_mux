"""`sufficiency_engine` is a disabled stub — pin it so nobody re-derives this.

The question this module answers, permanently: does a contract `sufficiency`
block do anything at runtime? **No.** `sufficiency_enabled()` is a hardcoded
`False` that no config key or env var reaches, and `evaluate()` returns an empty
finding set for every input, so no live path can fail a stage on a sufficiency
rule. Contract `sufficiency` entries are documentation.

The second half of the file is the reason that matters. Switching the engine on
without defusing it first would reintroduce exactly the hazard `inputs.hard`
had — a line in a YAML becoming a failed live stage — because
`validate_reuse_copy` consumes `evaluate` *unguarded* and turns a blocking
finding into a reuse error. `test_a_blocking_finding_would_become_a_live_error`
below is that latent path, demonstrated with the stub forced on.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from interview_mux import artifact_completeness, artifact_lifecycle, stage_acceptance
from interview_mux import sufficiency_engine as se
from interview_mux.file_store import write_json as fs_write_json
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx

SRC = Path(inspect.getfile(se)).resolve().parent
BRIEF_PATH = "understanding/content_brief.json"
STAGE = "content_context"


def _ctx(tmp_path: Path, name: str) -> RunContext:
    return isolated_run_ctx(tmp_path, name)


def _seed(ctx: RunContext, rel: str, doc: dict) -> None:
    dest = Path(ctx.run_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(dest, doc)


# ---------------------------------------------------------------------------
# The engine is off and cannot be switched on from outside the source
# ---------------------------------------------------------------------------

def test_sufficiency_is_disabled() -> None:
    assert se.sufficiency_enabled() is False
    assert se.evaluate(STAGE, {"anything": 1}, None) == {"findings": []}
    assert se.findings_to_gap_paths(["a", "b"]) == []


@pytest.mark.parametrize(
    "name",
    [
        "MUX_SUFFICIENCY",
        "MUX_SUFFICIENCY_ENABLED",
        "MUX_SUFFICIENCY_STRICT",
        "INTERVIEW_MUX_SUFFICIENCY",
        "ANALYSIS_SUFFICIENCY_ENABLED",
    ],
)
def test_no_env_var_switches_it_on(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(name, "1")
    assert se.sufficiency_enabled() is False


def test_no_config_or_env_is_even_read() -> None:
    """`analysis.sufficiency.enabled` is `true` in app.defaults.json and reaches nothing.

    A literal `return False` is the whole implementation; the parametrised env
    sweep above can only cover names somebody thought of, this covers the rest.
    """
    source = inspect.getsource(se)
    assert "os.environ" not in source and "getenv" not in source
    assert "app_config" not in source and "load_config" not in source
    body = inspect.getsource(se.sufficiency_enabled).rsplit('"""', 1)[-1]
    assert body.strip() == "return False"


# ---------------------------------------------------------------------------
# No live path can fail a stage on sufficiency
# ---------------------------------------------------------------------------

def test_every_guarded_caller_skips_the_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Forcing a blocking finding changes nothing while the gate is off."""
    monkeypatch.setattr(
        se, "evaluate", lambda *a, **k: {"findings": [{"blocking": True, "message": "no"}]}
    )
    monkeypatch.setattr(se, "findings_to_gap_paths", lambda findings: ["style.tone"])

    for module in (stage_acceptance.stage_acceptance_ok, artifact_lifecycle.build_outputs_view):
        src = inspect.getsource(module)
        assert "sufficiency_enabled()" in src, f"{module.__name__} lost its guard"

    gaps = artifact_completeness.compute_gaps(BRIEF_PATH, {"thesis": ""}, stage_key=STAGE)
    assert [g.path for g in gaps] != ["style.tone"], (
        "compute_gaps consulted the engine — its sufficiency_enabled() guard is gone"
    )


def test_contract_sufficiency_rules_are_documentation_only() -> None:
    """Contracts carry `sufficiency` rules; no runtime module reads them.

    `stage_contract.parse` builds `StageContract.sufficiency`, and the only
    readers are `tools/` and `tests/`. If this fails, some runtime module started
    consuming contract rules and the defusal question above is live again.
    """
    from interview_mux.stage_contract import load_contract

    contract = load_contract("content_context")
    assert contract is not None and contract.sufficiency, "fixture stage lost its rules"

    # `\b` excludes the module import (`.sufficiency_engine`) and the acceptance
    # field (`.sufficiency_errors`) — only attribute reads of the parsed rules match.
    attribute_read = re.compile(r"\.sufficiency\b")
    readers = [
        path.relative_to(SRC.parent.parent)
        for path in SRC.rglob("*.py")
        if path.name not in {"stage_contract.py", "sufficiency_engine.py"}
        and attribute_read.search(path.read_text(encoding="utf-8"))
    ]
    assert not readers, f"contract sufficiency rules are consumed at runtime by {readers}"


# ---------------------------------------------------------------------------
# The hazard a future worker would reintroduce
# ---------------------------------------------------------------------------

def test_a_blocking_finding_would_become_a_live_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`validate_reuse_copy` calls `evaluate` with no `sufficiency_enabled()` guard.

    Only the stub's empty return keeps it inert. Switch the engine on and this is
    a contract rule failing a live reuse — defuse it the way
    `artifact_lifecycle._missing_hard_input` defuses an absent hard input first.
    """
    ctx = _ctx(tmp_path, "suff_reuse")
    _seed(ctx, BRIEF_PATH, {"thesis": "x"})
    monkeypatch.setattr(
        "interview_mux.prompt_validation.validate_artifact_write", lambda rel, doc: []
    )

    assert artifact_lifecycle.validate_reuse_copy(ctx, STAGE, "exec_prior") == []

    monkeypatch.setattr(
        se,
        "evaluate",
        lambda *a, **k: {"findings": [{"blocking": True, "message": "thesis too thin"}]},
    )
    errors = artifact_lifecycle.validate_reuse_copy(ctx, STAGE, "exec_prior")
    assert errors == ["thesis too thin"]
