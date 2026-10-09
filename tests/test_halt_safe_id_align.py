"""Manifest ids follow saved boundaries, and retired ids leave the flush files."""

from interview_mux.artifact_completeness import (
    aligned_manifest_segments,
    strip_retired_segment_ids,
)
from interview_mux.segment_id_remap import _restore_vo_pair


def test_aligned_manifest_keeps_the_saved_row_and_drops_a_retired_id() -> None:
    rows = [
        {"segment_id": "seg_002", "start_ms": 80, "end_ms": 4000, "speaker_id": "spk_1"},
        {"segment_id": "seg_003", "start_ms": 4080, "end_ms": 9000},
    ]
    existing = [
        {"segment_id": "seg_001", "text": "old", "type": "interviewee_answer"},
        {"segment_id": "seg_002", "text": "kept", "type": "interviewee_answer"},
    ]
    aligned = aligned_manifest_segments(rows, existing)
    assert [row["segment_id"] for row in aligned] == ["seg_002", "seg_003"]
    assert aligned[0]["text"] == "kept"
    assert aligned[0]["speaker_id"] == "spk_1"
    assert aligned[1]["start_ms"] == 4080


def test_strip_retired_ids_from_brief_narrative_and_soundscape() -> None:
    live = {"seg_002"}
    brief = strip_retired_segment_ids(
        {
            "topics": [{"segment_ids": ["seg_001", "seg_002"]}],
            "key_claims": [{"evidence_segment_ids": ["seg_009"]}],
        },
        live,
    )
    assert brief["topics"][0]["segment_ids"] == ["seg_002"]
    assert brief["key_claims"][0]["evidence_segment_ids"] == []
    narrative = strip_retired_segment_ids(
        {"chapters": [{"segment_ids": ["seg_001", "seg_002"]}]},
        live,
    )
    assert narrative["chapters"][0]["segment_ids"] == ["seg_002"]
    policy = strip_retired_segment_ids(
        {"cue_slots": [{"segment_id": "seg_001"}, {"segment_id": "seg_002"}]},
        live,
    )
    assert policy["cue_slots"] == [{"segment_id": "seg_002"}]


class _Ctx:
    def __init__(self) -> None:
        self.written: dict[str, dict] = {}
        self.logs: list[str] = []

    def write_json(self, rel: str, doc: dict, **_kwargs) -> None:
        self.written[rel] = doc

    def log(self, message: str, **_kwargs) -> None:
        self.logs.append(message)


def test_vo_pair_restores_the_file_that_landed_when_its_partner_did_not() -> None:
    ctx = _Ctx()
    gap = "understanding/gap_report.json"
    plan = "mastering/mastering_plan.json"
    before = {
        gap: {"lines": [{"targets_segment_id": "seg_001"}]},
        plan: {"clips": [{"segment_id": "seg_001"}]},
    }
    updated = [gap]
    _restore_vo_pair(
        ctx,
        {"seg_001": "seg_002"},
        before,
        updated,
        stage_key="connector_fuse_pass",
    )
    assert ctx.written[gap]["lines"][0]["targets_segment_id"] == "seg_001"
    assert gap not in updated
    assert plan not in ctx.written
