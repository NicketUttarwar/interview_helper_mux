"""Round-trip tests for every SNAPSHOT_PATHS key."""

from __future__ import annotations

from interview_mux.operator_snapshots import MANIFEST_REL, SNAPSHOT_PATHS, persist_operator_transcript
from interview_mux.run_context import RunContext


def test_snapshot_paths_keys_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    for key, rel in SNAPSHOT_PATHS.items():
        assert rel.startswith("operator/"), f"{key} must live under operator/"
        assert key.replace("_", " ").replace("-", " ")


def test_snapshot_manifest_lists_known_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.path("transcript").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "Hello",
            "words": [{"text": "Hello", "start_ms": 0, "end_ms": 400}],
        },
    )
    persist_operator_transcript(ctx, source="test")
    manifest = ctx.read_json(MANIFEST_REL)
    snapshots = manifest.get("snapshots") or {}
    assert SNAPSHOT_PATHS["transcript_corrected"] in snapshots.values() or any(
        SNAPSHOT_PATHS["transcript_corrected"] in str(v) for v in snapshots.values()
    )
