"""Wave 8 — assert every residual catalog Done-when has named proofs."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    from tests.rstm.enumerate_matrix import coverage_gate, enumerate_matrix
    from tests.rstm.residual_cluster_scorecard import (
        DILUTION_WATCH,
        DONE_WHEN_CATALOG,
        INLINE_SMOKES,
        REQUIRED_IDS,
        run_all_inline_smokes,
    )
except ModuleNotFoundError:
    from enumerate_matrix import coverage_gate, enumerate_matrix  # type: ignore
    from residual_cluster_scorecard import (  # type: ignore
        DILUTION_WATCH,
        DONE_WHEN_CATALOG,
        INLINE_SMOKES,
        REQUIRED_IDS,
        run_all_inline_smokes,
    )

ROOT = Path(__file__).resolve().parents[2]


def _split_pytest_nodeid(nodeid: str) -> tuple[Path, str]:
    """Return (file_path, function_name) from pytest nodeid."""
    # tests/foo.py::test_bar or tests/foo.py::test_bar[param]
    left, _, right = nodeid.partition("::")
    path = ROOT / left
    func = right.split("[", 1)[0].strip()
    return path, func


def test_required_ids_match_catalog_keys() -> None:
    assert REQUIRED_IDS == frozenset(DONE_WHEN_CATALOG.keys())
    assert len(REQUIRED_IDS) == 40


def test_every_id_has_at_least_one_proof() -> None:
    missing = [cid for cid, row in DONE_WHEN_CATALOG.items() if not (row.get("proofs") or [])]
    assert not missing, f"IDs missing proofs: {missing}"


def test_pytest_proofs_exist_and_name_in_file() -> None:
    errors: list[str] = []
    for cid, row in sorted(DONE_WHEN_CATALOG.items()):
        for proof in row.get("proofs") or []:
            if proof.get("kind") != "pytest":
                continue
            nodeid = str(proof.get("nodeid") or "")
            path, func = _split_pytest_nodeid(nodeid)
            if not path.is_file():
                errors.append(f"{cid}: missing file {path}")
                continue
            text = path.read_text(encoding="utf-8")
            if f"def {func}" not in text:
                errors.append(f"{cid}: {func} not found in {path.relative_to(ROOT)}")
    assert not errors, "\n".join(errors)


def test_vitest_proofs_files_exist() -> None:
    errors: list[str] = []
    for cid, row in sorted(DONE_WHEN_CATALOG.items()):
        for proof in row.get("proofs") or []:
            if proof.get("kind") != "vitest":
                continue
            rel = str(proof.get("path") or "")
            path = ROOT / rel
            if not path.is_file():
                errors.append(f"{cid}: missing vitest file {rel}")
    assert not errors, "\n".join(errors)


def test_inline_proofs_registered_and_run() -> None:
    names: list[str] = []
    for row in DONE_WHEN_CATALOG.values():
        for proof in row.get("proofs") or []:
            if proof.get("kind") == "inline":
                names.append(str(proof["nodeid"]))
    unknown = [n for n in names if n not in INLINE_SMOKES]
    assert not unknown, f"inline proofs not registered: {unknown}"
    ran = run_all_inline_smokes()
    assert set(names).issubset(set(ran))


def test_dilution_watch_parents_in_catalog() -> None:
    assert len(DILUTION_WATCH) == 9
    for item in DILUTION_WATCH:
        parent = item["parent"]
        assert parent in DONE_WHEN_CATALOG, f"dilution parent missing: {parent}"
        for extra in item.get("also_parents") or []:
            assert extra in DONE_WHEN_CATALOG


def test_enumerate_coverage_residual_donewhen() -> None:
    meta = enumerate_matrix()
    assert meta["coverage"].get("residual_donewhen") is True
    coverage_gate(meta)
    rc = [c for c in meta["cells"] if c["tier"] == "RC-DW"]
    covered = {c["cluster"] for c in rc}
    assert REQUIRED_IDS.issubset(covered)
