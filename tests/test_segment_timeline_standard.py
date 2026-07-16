from __future__ import annotations

from interview_mux.segment_timeline_standard import (
    format_shard_identity,
    normalize_shard_envelope,
    reject_or_repair_shard,
    validate_boundary_timeline,
)


def test_format_shard_identity_boundary_span():
    shard = {"label": "time_2", "start_ms": 8210, "end_ms": 102260}
    env = {
        "artifacts": {
            "boundaries": [
                {"segment_id": "seg_001", "start_ms": 8210, "end_ms": 9000, "speaker_id": "spk_0"},
                {"segment_id": "seg_002", "start_ms": 9000, "end_ms": 102260, "speaker_id": "spk_1"},
            ]
        }
    }
    identity = format_shard_identity(shard, "boundary_detection", env)
    assert "time_2" in identity
    assert "8210" in identity
    assert "102260" in identity
    assert "2 boundaries" in identity
    assert identity != "n/a"


def test_format_shard_identity_classification_segments():
    shard = {"label": "batch_1", "segment_ids": ["seg_001", "seg_002"]}
    identity = format_shard_identity(shard, "segment_classification", {})
    assert "seg_001" in identity
    assert "seg_002" in identity


def test_reject_or_repair_shard_missing_speaker():
    env = {
        "artifacts": {
            "boundaries": [
                {"segment_id": "seg_001", "start_ms": 0, "end_ms": 500},
            ]
        }
    }
    normalized = normalize_shard_envelope(env, {"label": "time_1"})
    result = reject_or_repair_shard("boundary_detection", normalized)
    assert result.rejected is True
    assert result.errors


def test_validate_boundary_timeline_clean():
    rows = [
        {"segment_id": "seg_001", "start_ms": 0, "end_ms": 500, "speaker_id": "spk_0"},
        {"segment_id": "seg_002", "start_ms": 500, "end_ms": 1200, "speaker_id": "spk_1"},
    ]
    assert not validate_boundary_timeline(rows)
