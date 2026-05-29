import json
from pathlib import Path

from cursor_execute.errors import RunFailure, write_last_failure


def test_last_failure_json(tmp_path: Path):
    failure = RunFailure(
        exit_code=3,
        phase="parse",
        message="test failure",
        command_index=1,
        command_id="GC-T1",
    )
    write_last_failure(tmp_path, failure)
    data = json.loads((tmp_path / "last_failure.json").read_text())
    assert data["exit_code"] == 3
    assert data["phase"] == "parse"
