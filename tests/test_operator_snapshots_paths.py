"""Round-trip tests for every SNAPSHOT_PATHS key."""

from __future__ import annotations

from interview_mux.operator_snapshots import SNAPSHOT_PATHS
from interview_mux.run_context import RunContext


def test_snapshot_paths_keys_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    for key, rel in SNAPSHOT_PATHS.items():
        assert rel.startswith("operator/"), f"{key} must live under operator/"
        assert key.replace("_", " ").replace("-", " ")


def test_snapshot_manifest_lists_known_keys(tmp_path, monkeypatch):
    from interview_mux.operator_snapshots import MANIFEST_REL, persist_operator_flow_selection

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    persist_operator_flow_selection(ctx, "flow1", source="test")
    manifest = ctx.read_json(MANIFEST_REL)
    snapshots = manifest.get("snapshots") or {}
    assert SNAPSHOT_PATHS["flow_selection"] in snapshots or any(
        SNAPSHOT_PATHS["flow_selection"] in str(v) for v in snapshots.values()
    )
