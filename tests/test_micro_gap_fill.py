from __future__ import annotations

from interview_mux.micro_gap_fill import compose_patch_schema, paths_from_findings, run_micro_gap_fill
from interview_mux.sufficiency_engine import SufficiencyFinding


class _Ctx:
    def __init__(self) -> None:
        self._data: dict = {}

    def artifact_exists(self, rel: str) -> bool:
        return rel in self._data

    def read_json(self, rel: str):
        return self._data.get(rel)

    def write_json(self, rel: str, data, **kwargs):
        self._data[rel] = data


def test_compose_patch_schema_subset():
    schema = compose_patch_schema("content_context", ["thesis"])
    props = schema["properties"]["artifacts"]["properties"]
    assert "thesis" in props
    assert "topics" not in props


def test_run_micro_gap_fill_records_plan():
    ctx = _Ctx()
    finding = SufficiencyFinding("thesis", "non_empty_string", __import__(
        "interview_mux.sufficiency_engine", fromlist=["BlockingTier"]
    ).BlockingTier.PROGRESSION, "thesis empty")
    paths = paths_from_findings([finding])
    art, errs = run_micro_gap_fill(ctx, "content_context", paths, existing={"thesis": ""})
    assert not errs
    assert art.get("_meta", {}).get("micro_gap_fill_plan")


def test_paths_from_findings():
    f = SufficiencyFinding("topics", "min_rows", __import__(
        "interview_mux.sufficiency_engine", fromlist=["BlockingTier"]
    ).BlockingTier.PROGRESSION, "need topics")
    assert paths_from_findings([f]) == ["topics"]
