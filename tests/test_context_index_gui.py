import shutil
from pathlib import Path

import pytest

from interview_mux.context_index_gui import (
    create_volley_entry,
    get_context_index_summary,
    invalidate_volley_entry,
    put_volley_entry,
)
from interview_mux.run_context import RunContext

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "minimal_run"
RUN_ID = "exec_001_a1b2c3d4e5f6_20260601T120000Z"


@pytest.fixture
def ctx(tmp_path):
    import shutil

    from tests.run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, RUN_ID)
    shutil.copytree(FIXTURE, ctx.run_dir, dirs_exist_ok=True)
    return ctx


def test_context_index_api_helpers(ctx):
    summary = get_context_index_summary(ctx)
    assert "stats" in summary
    entry = create_volley_entry(
        ctx,
        {"content": "Manual operator conclusion.", "kind": "stage_conclusion"},
    )
    assert entry.get("entry_id")
    updated = put_volley_entry(ctx, entry["entry_id"], {"content": "Edited conclusion."})
    assert updated["operator_edited"] is True
    assert "Edited" in updated["content"]
    inv = invalidate_volley_entry(ctx, entry["entry_id"])
    assert inv["status"] == "invalidated"
