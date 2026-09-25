from __future__ import annotations

from pathlib import Path

from interview_mux.speaker_delivery_plan import (
    episode_vo_identity,
    stamp_episode_vo_identity,
    vo_shape_to_pov,
)


def test_vo_shape_to_pov_defaults_third_person() -> None:
    assert vo_shape_to_pov("third_person") == "expository_third_person"
    assert vo_shape_to_pov("host_second_person") == "host_second_person"


def test_episode_vo_identity_uses_clone_and_opener_shape(tmp_path: Path) -> None:
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "vo_lock")
    ctx.write_json(
        "understanding/speaker_delivery_plan.json",
        {"clone_speaker_id": "spk_0", "vo_shape": "host_second_person"},
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_opening",
                    "episode_orientation": True,
                    "line_category": "episode_preface",
                    "gap_type": "missing_orientation",
                    "vo_shape": "third_person",
                    "text": "Mohan joins us to examine blood-based testing.",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                }
            ]
        },
    )
    ident = episode_vo_identity(ctx)
    assert ident["speaker_id"] == "spk_0"
    assert ident["vo_shape"] == "third_person"
    assert ident["ref_wav"].endswith("spk_0.wav")
    stamped = stamp_episode_vo_identity(
        ctx, {"line_id": "vo_layup_seg_036", "vo_shape": "host_first_person"}
    )
    assert stamped["voice_speaker_id"] == "spk_0"
    assert stamped["vo_shape"] == "third_person"


def test_chatterbox_synthesize_retries_locked_ref_only(tmp_path, monkeypatch) -> None:
    from interview_mux import chatterbox_runner
    from interview_mux.local_runtime import LocalRuntimeUnavailable
    from run_fixtures import (
        confirm_test_pickup_speaker,
        isolated_run_ctx,
        write_fixture_json,
        write_fixture_vo_wav,
    )

    ctx = isolated_run_ctx(tmp_path, "cb_lock")
    confirm_test_pickup_speaker(ctx, speaker_id="spk_0")
    write_fixture_vo_wav(
        ctx.final_path("understanding", "speaker_samples", "spk_0.wav"),
        duration_sec=3.2,
    )
    write_fixture_json(
        ctx,
        "understanding/voice_reference/spk_0.json",
        {
            "speaker_id": "spk_0",
            "approved": True,
            "wav": "understanding/speaker_samples/spk_0.wav",
        },
    )
    write_fixture_json(
        ctx,
        "run_meta.json",
        {
            "gap_framing_enabled": True,
            "gap_vo_delivery": "chatterbox",
            "voice_reference_approved_at": "2026-01-01T00:00:00Z",
        },
    )
    sample = ctx.path("understanding", "speaker_samples", "spk_0.wav")
    alt = ctx.path("understanding", "voice_reference", "clips", "spk_0", "candidate_00.wav")
    alt.parent.mkdir(parents=True, exist_ok=True)
    alt.write_bytes(b"\x01" * 100)
    ctx.write_json(
        "understanding/speaker_delivery_plan.json",
        {"clone_speaker_id": "spk_0"},
    )

    seen: list[str] = []

    def _once(ctx, line, *, ref, out_wav, voice_ref_id, attempt):
        seen.append(str(Path(ref).name) + f":{voice_ref_id}:{attempt}")
        raise LocalRuntimeUnavailable("synth down")

    monkeypatch.setattr(chatterbox_runner, "_synthesize_once", _once)
    monkeypatch.setattr(chatterbox_runner, "chatterbox_enabled", lambda: True)
    monkeypatch.setattr(
        chatterbox_runner,
        "_iter_voice_ref_candidates",
        lambda _ctx, _line: [
            ("speaker_sample", sample),
            ("candidate_00", alt),
        ],
    )

    line = {"line_id": "vo_x", "text": "Hello there.", "voice_speaker_id": "spk_0"}
    try:
        chatterbox_runner.synthesize_line(ctx, line)
    except LocalRuntimeUnavailable:
        pass
    assert seen
    assert all("candidate_00" not in row for row in seen)
    assert all(row.startswith("spk_0.wav:speaker_sample:") for row in seen)
