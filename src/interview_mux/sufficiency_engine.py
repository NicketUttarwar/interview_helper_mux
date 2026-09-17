"""Legacy sufficiency stubs — disabled in v2.

**Nothing here checks anything.** `evaluate()` returns an empty finding set for
every input, so the `sufficiency` block of a stage contract is *documentation
only*: it describes what a good artifact looks like and no live run consults it.
Every caller is either guarded by `sufficiency_enabled()`
(`stage_acceptance.stage_acceptance_ok`, `artifact_completeness.compute_gaps`,
`artifact_lifecycle.build_outputs_view`) or reads the empty findings and appends
nothing (`artifact_lifecycle.validate_reuse_copy`). `analysis.sufficiency.*` in
`config/app.defaults.json` is read by no code. Pinned by
`tests/test_sufficiency_engine_disabled.py`.

Before switching any of this on: **defuse it first.** A contract rule that
becomes a live check inherits the hazard `inputs.hard` had — a declaration in a
YAML turning into a failed live stage. `artifact_lifecycle.hard_input_strict` /
`_missing_hard_input` is the pattern to mirror (record a refusal by default,
kill switch restores strict).
"""

from __future__ import annotations

from typing import Any


def sufficiency_enabled(*_args: Any, **_kwargs: Any) -> bool:
    """DISABLED. Hardcoded `False` — no config key and no env var switches it on.

    Contract `sufficiency` entries are therefore documentation, not a runtime gate.
    """
    return False


def evaluate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """DISABLED — always "no findings", so no caller can fail a stage on this."""
    return {"findings": []}


def findings_to_gap_paths(findings: list[Any]) -> list[str]:
    _ = findings
    return []
