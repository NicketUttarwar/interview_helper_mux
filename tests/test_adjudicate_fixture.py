"""13B — minimal synthetic adjudicate path fixture loads for CI."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.vo_line_adjudicate import lines_needing_adjudicate
from run_fixtures import isolated_run_ctx

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "adjudicate_path" / "minimal.json"


def test_minimal_adjudicate_fixture_loads(tmp_path: Path) -> None:
    blob = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ctx = isolated_run_ctx(tmp_path, "adj_fixture")
    ctx.write_json("run_meta.json", blob["run_meta"], skip_handoff=True)
    for rel, doc in blob.items():
        if rel in {"version", "description", "run_meta"}:
            continue
        path = ctx.final_path(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        import json as _json

        path.write_text(_json.dumps(doc), encoding="utf-8")
    gap = ctx.read_json("understanding/gap_report.json")
    needing = lines_needing_adjudicate(ctx, gap)
    assert len(needing) >= 1
    assert needing[0].get("line_id") == "vo_fixture_layup"
