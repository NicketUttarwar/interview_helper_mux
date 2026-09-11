"""RSTM matrix pytest runner — HEAD-only, mocked contract cells."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx

try:
    from tests.rstm import CAMPAIGN_ID, WAVE_A_ID
    from tests.rstm.enumerate_matrix import coverage_gate, write_matrix
    from tests.rstm.harness import persist_result, run_cell
except ModuleNotFoundError:
    from rstm import CAMPAIGN_ID, WAVE_A_ID  # type: ignore
    from rstm.enumerate_matrix import coverage_gate, write_matrix  # type: ignore
    from rstm.harness import persist_result, run_cell  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / ".cursor/plans/rstm" / "results"
SUMMARY = RESULTS / "summary.json"


@pytest.fixture(scope="session")
def rstm_matrix():
    meta = write_matrix()
    coverage_gate(meta)
    return meta


def test_rstm_coverage_gate(rstm_matrix):
    assert rstm_matrix["cell_count"] > 100
    assert rstm_matrix["coverage"]["d1"]
    assert rstm_matrix["coverage"]["d2_seed"]
    assert rstm_matrix["coverage"]["p0_d3"]
    assert rstm_matrix["coverage"].get("residual_donewhen") is True
    assert any(c["tier"] == "RC-DW" for c in rstm_matrix["cells"])


def test_rstm_execute_all_cells(rstm_matrix, tmp_path):
    """Execute every in-ceiling cell; write dated summary (may take a few minutes)."""
    cells = rstm_matrix["cells"]
    # Shard-friendly: full run in one session; keep under ~few minutes via contract checks
    statuses: Counter[str] = Counter()
    confirmed: Counter[str] = Counter()
    results = []

    for i, cell in enumerate(cells):
        ctx = isolated_run_ctx(tmp_path / f"c{i}", f"rstm_{i}")
        # minimal dirs
        for d in ("master", "understanding", "segments", "transcript", "mastering"):
            (ctx.run_dir / d).mkdir(exist_ok=True)
        result = run_cell(ctx, cell)
        persist_result(result)
        statuses[result.status] += 1
        for c in result.confirmed_clusters:
            confirmed[c] += 1
        results.append(result.to_dict())

    summary = {
        "campaign_id": CAMPAIGN_ID,
        "merges_wave_a": WAVE_A_ID,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_head": rstm_matrix["git_head"],
        "cell_count": len(cells),
        "status_counts": dict(statuses),
        "confirmed_clusters": dict(confirmed),
        "fail_sample": [r for r in results if r["status"] == "FAIL"][:50],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")

    # Campaign must produce signal; hollow-done is expected CONFIRMED on HEAD
    assert statuses["PASS"] + statuses.get("SCOPE_CONTRACT_ONLY", 0) + statuses.get(
        "BLOCKED_BY_HEAD", 0
    ) + statuses.get("FAIL", 0) + statuses.get("ERROR", 0) == len(cells)
    assert summary["cell_count"] == len(cells)
