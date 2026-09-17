"""Seed↔contract alignment ratchet (0.2.0 leapfrog footgun)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_audit():
    path = ROOT / "tools" / "audit_seed_contract_alignment.py"
    name = "audit_seed_contract_alignment"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_audit_flags_topology_content_context_soft_underdeclare():
    """D14 thrash class must stay visible until SEED_ORDER promote lands."""
    mod = _load_audit()
    findings = mod.audit()
    forbidden = [
        f
        for f in findings
        if f.producer == "source_topology_build" and f.consumer == "content_context"
    ]
    # After promote, this should be empty; while soft, must fail closed.
    from interview_mux.stage_contract import load_contract

    c = load_contract("content_context")
    assert c is not None
    topo_hard = any(
        d.hard and d.path == "understanding/source_topology.json" for d in c.inputs
    )
    if topo_hard:
        assert not forbidden
    else:
        assert forbidden, "topology→content_context soft under-declare must be flagged"


def test_audit_script_exit_matches_findings():
    mod = _load_audit()
    findings = mod.audit()
    code = mod.main([])
    assert code == (1 if findings else 0)


def test_forbidden_pairs_never_on_allowlist():
    mod = _load_audit()
    for pair in mod.FORBIDDEN_SOFT_UNDERDECLARE:
        assert pair not in mod.CONSECUTIVE_SOFT_ALLOWLIST
